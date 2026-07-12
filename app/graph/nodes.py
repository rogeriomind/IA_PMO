from __future__ import annotations

import logging
from typing import Any

from app.graph.state import AgentState
from app.mcp.board_tools import drop_none
from app.observability.langfuse import LangfuseTracer, TraceContext
from app.schemas import Intent
from app.services.confirmation_service import ConfirmationService
from app.services.intent_service import IntentService
from app.services.pending_action_service import PendingActionService
from app.services.response_service import ResponseService

logger = logging.getLogger(__name__)


class AgentGraphNodes:
    def __init__(
        self,
        *,
        intent_service: IntentService,
        pending_actions: PendingActionService,
        response_service: ResponseService,
        board_tools: Any,
        confirmation_service: ConfirmationService,
        tracer: LangfuseTracer,
    ):
        self.intent_service = intent_service
        self.pending_actions = pending_actions
        self.response_service = response_service
        self.board_tools = board_tools
        self.confirmation_service = confirmation_service
        self.tracer = tracer

    async def load_context(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        with self.tracer.span(trace, "load_context", input_payload={"channel": state.get("channel")}):
            return {
                "request_metadata": state.get("request_metadata") or {},
                "requires_confirmation": False,
                "missing_fields": [],
                "trace_id": trace.trace_id if isinstance(trace, TraceContext) else state.get("trace_id"),
            }

    async def classify_intent(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        with self.tracer.span(trace, "classify_intent", input_payload={"message": state.get("message")}):
            result = await self.intent_service.classify(state["message"], trace=trace)
            self.tracer.update_trace(
                trace,
                metadata={
                    "intent": result.intent.value,
                    "confidence": result.confidence,
                    "channel": state.get("channel"),
                    "project_id": (state.get("request_metadata") or {}).get("project_id"),
                },
            )
            return {"intent": result.intent, "confidence": result.confidence}

    async def route_by_intent(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        intent = state.get("intent", Intent.UNKNOWN)
        with self.tracer.span(trace, "route_by_intent", metadata={"intent": intent.value}):
            if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION}:
                return {"route": "read"}
            if intent in {Intent.TASK_CREATE, Intent.TASK_UPDATE, Intent.TASK_MOVE, Intent.TASK_COMMENT}:
                return {"route": "write"}
            return {"route": "respond"}

    async def call_mcp_read_tool(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        intent = state.get("intent", Intent.UNKNOWN)
        metadata = state.get("request_metadata") or {}
        project_id = metadata.get("project_id")

        with self.tracer.span(trace, "call_mcp_read_tool", metadata={"intent": intent.value, "project_id": project_id}):
            try:
                if intent == Intent.STATUS_BOARD:
                    result = await self.board_tools.get_project_status(project_id=project_id, query=state.get("message"))
                elif "minhas" in state.get("message", "").casefold():
                    result = await self.board_tools.list_my_tasks(user_id=state["user_id"], project_id=project_id)
                elif "bloque" in state.get("message", "").casefold():
                    result = await self.board_tools.list_blockers(project_id=project_id)
                else:
                    result = await self.board_tools.search_tasks(query=state.get("message", ""), project_id=project_id)
                return {"board_context": result}
            except Exception:
                logger.exception("MCP read tool failed")
                return {
                    "board_context": None,
                    "error": "mcp_read_failed",
                    "final_message": "Nao consegui consultar o board agora. A integracao MCP nao retornou dados suficientes.",
                }

    async def extract_entities(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        intent = state.get("intent", Intent.UNKNOWN)
        with self.tracer.span(trace, "extract_entities", metadata={"intent": intent.value}):
            entities = await self.intent_service.extract_entities(state["message"], intent, trace=trace)
            return {"entities": entities.model_dump(exclude_none=True)}

    async def validate_required_fields(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        intent = state.get("intent", Intent.UNKNOWN)
        entities = state.get("entities") or {}
        missing: list[str] = []

        with self.tracer.span(trace, "validate_required_fields", metadata={"intent": intent.value}):
            if intent == Intent.TASK_CREATE:
                if not entities.get("title"):
                    missing.append("title")
            elif intent == Intent.TASK_UPDATE:
                if not (entities.get("task_id") or entities.get("task_query")):
                    missing.append("task")
                if not entities.get("fields"):
                    missing.append("fields")
            elif intent == Intent.TASK_MOVE:
                if not (entities.get("task_id") or entities.get("task_query")):
                    missing.append("task")
                if not entities.get("status"):
                    missing.append("status")
            elif intent == Intent.TASK_COMMENT:
                if not (entities.get("task_id") or entities.get("task_query")):
                    missing.append("task")
                if not entities.get("comment"):
                    missing.append("comment")
            return {"missing_fields": missing}

    async def prepare_pending_action(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        intent = state.get("intent", Intent.UNKNOWN)
        entities = state.get("entities") or {}
        metadata = state.get("request_metadata") or {}

        with self.tracer.span(trace, "prepare_pending_action", metadata={"intent": intent.value}):
            if state.get("missing_fields"):
                return {"requires_confirmation": False, "action": None, "pending_action_id": None}

            payload = self._payload_for_intent(intent, entities, metadata)
            pending = self.pending_actions.create_from_intent(
                conversation_id=state["conversation_id"],
                user_id=state["user_id"],
                intent=intent,
                payload=payload,
            )
            action = {"type": pending["action_type"], "payload": payload}
            return {
                "requires_confirmation": True,
                "pending_action_id": pending["id"],
                "action": action,
            }

    async def ask_confirmation(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        with self.tracer.span(trace, "ask_confirmation"):
            if state.get("missing_fields"):
                return {
                    "final_message": self.response_service.missing_fields_message(
                        state.get("intent", Intent.UNKNOWN),
                        state.get("missing_fields") or [],
                        state.get("entities") or {},
                    )
                }
            action = state.get("action") or {}
            return {"final_message": self.response_service.confirmation_message(action)}

    async def generate_response(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        intent = state.get("intent", Intent.UNKNOWN)
        with self.tracer.span(trace, "generate_response", metadata={"intent": intent.value}):
            if state.get("final_message"):
                return {}
            if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION}:
                return {"final_message": self.response_service.read_response(intent, state.get("board_context"))}
            if intent == Intent.SMALLTALK:
                return {"final_message": self.response_service.smalltalk_response()}
            if intent == Intent.UNKNOWN:
                return {"final_message": self.response_service.unknown_response()}
            return {"final_message": self.response_service.error_response()}

    async def load_pending_action(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        with self.tracer.span(trace, "load_pending_action", input_payload={"pending_action_id": state.get("pending_action_id")}):
            pending = self.pending_actions.get(state["pending_action_id"])
            return {"pending_action": pending}

    async def execute_mcp_write_tool(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        pending = state.get("pending_action")
        with self.tracer.span(
            trace,
            "execute_mcp_write_tool",
            metadata={"action_type": pending.get("action_type") if pending else None},
        ):
            executed, board_result, message = await self.confirmation_service.confirm_and_execute(
                pending_action_id=state["pending_action_id"],
                conversation_id=state["conversation_id"],
                user_id=state["user_id"],
                confirmed=bool(state.get("confirmed")),
            )
            return {"executed": executed, "board_result": board_result, "final_message": message}

    async def generate_confirmation_response(self, state: AgentState) -> AgentState:
        trace = state.get("_trace")
        with self.tracer.span(trace, "generate_response", metadata={"confirmation": True}):
            if state.get("final_message"):
                return {}
            return {"final_message": self.response_service.error_response(), "executed": False}

    @staticmethod
    def _payload_for_intent(intent: Intent, entities: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        project = entities.get("project") or metadata.get("project_id")
        if intent == Intent.TASK_CREATE:
            return drop_none(
                {
                    "title": entities.get("title"),
                    "description": entities.get("description"),
                    "assignee": entities.get("assignee"),
                    "priority": entities.get("priority"),
                    "due_date": entities.get("due_date"),
                    "project": project,
                    "status": entities.get("status"),
                }
            )
        if intent == Intent.TASK_UPDATE:
            return drop_none(
                {
                    "task_id": entities.get("task_id"),
                    "task_query": entities.get("task_query"),
                    "fields": entities.get("fields") or {},
                    "project": project,
                }
            )
        if intent == Intent.TASK_MOVE:
            return drop_none(
                {
                    "task_id": entities.get("task_id"),
                    "task_query": entities.get("task_query"),
                    "status": entities.get("status"),
                    "project": project,
                }
            )
        if intent == Intent.TASK_COMMENT:
            return drop_none(
                {
                    "task_id": entities.get("task_id"),
                    "task_query": entities.get("task_query"),
                    "comment": entities.get("comment"),
                    "project": project,
                }
            )
        return {}

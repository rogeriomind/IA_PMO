from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.graph.builder import build_confirmation_graph, build_invoke_graph
from app.graph.nodes import AgentGraphNodes
from app.mcp.board_tools import BoardTools
from app.mcp.board_tools import normalize_priority, normalize_status
from app.mcp.client import MCPBoardClient
from app.observability.langfuse import LangfuseTracer
from app.schemas import (
    AgentAction,
    AgentConfirmRequest,
    AgentConfirmResponse,
    AgentInvokeRequest,
    AgentInvokeResponse,
    ExternalAgentProcessRequest,
    ExternalAgentProcessResponse,
    ExternalBoardAction,
    HealthResponse,
    Intent,
)
from app.services.confirmation_service import ConfirmationService
from app.services.intent_service import IntentService
from app.services.pending_action_service import PendingActionService
from app.services.response_service import ResponseService
from app.storage.repository import PendingActionRepository

logger = logging.getLogger(__name__)


LEGACY_INTENT_BY_INTENT = {
    Intent.TASK_CREATE: "create_task",
    Intent.TASK_UPDATE: "update_task",
    Intent.TASK_MOVE: "move_activity",
    Intent.TASK_COMMENT: "add_comment",
    Intent.STATUS_BOARD: "query_tasks",
    Intent.BOARD_QUESTION: "query_tasks",
    Intent.SMALLTALK: "unknown",
    Intent.UNKNOWN: "unknown",
}

LEGACY_ACTION_BY_INTENT = {
    Intent.TASK_CREATE: "create_activity",
    Intent.TASK_UPDATE: "update_activity",
    Intent.TASK_MOVE: "move_activity",
    Intent.TASK_COMMENT: "add_comment",
    Intent.STATUS_BOARD: "query_activities",
    Intent.BOARD_QUESTION: "query_activities",
    Intent.SMALLTALK: "unknown",
    Intent.UNKNOWN: "unknown",
}


def create_app(
    *,
    settings: Settings | None = None,
    board_tools_override: Any | None = None,
    repository_override: PendingActionRepository | None = None,
) -> FastAPI:
    settings_override = settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings = settings_override or get_settings()
        logging.basicConfig(
            level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

        repository = repository_override or PendingActionRepository(app_settings)
        repository.init_db()

        mcp_client = MCPBoardClient(app_settings)
        board_tools = board_tools_override or BoardTools(mcp_client)
        tracer = LangfuseTracer(app_settings)
        intent_service = IntentService(app_settings)
        response_service = ResponseService()
        pending_actions = PendingActionService(repository)
        confirmation_service = ConfirmationService(pending_actions, board_tools)
        nodes = AgentGraphNodes(
            intent_service=intent_service,
            pending_actions=pending_actions,
            response_service=response_service,
            board_tools=board_tools,
            confirmation_service=confirmation_service,
            tracer=tracer,
        )

        app.state.settings = app_settings
        app.state.repository = repository
        app.state.mcp_client = mcp_client
        app.state.board_tools = board_tools
        app.state.tracer = tracer
        app.state.intent_service = intent_service
        app.state.invoke_graph = build_invoke_graph(nodes)
        app.state.confirm_graph = build_confirmation_graph(nodes)

        if not app_settings.llm_configured:
            logger.warning(
                "LLM is not fully configured. Set AI_PROVIDER plus provider API key and model."
            )
        else:
            logger.info(
                "LLM configured from environment: provider=%s model=%s",
                app_settings.llm_provider,
                app_settings.llm_model,
            )

        if not mcp_client.mcp_loaded:
            logger.warning("MCP board tools are not fully loaded: %s", mcp_client.registry.error)

        try:
            yield
        finally:
            tracer.flush()

    api = FastAPI(title="PMO AI Agent API", version="0.1.0", lifespan=lifespan)

    @api.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        app_settings: Settings = api.state.settings
        mcp_client: MCPBoardClient = api.state.mcp_client
        checks: dict[str, Any] = {
            "llm_provider": app_settings.llm_provider,
            "llm_configured": app_settings.llm_configured,
            "mcp_doc_path": app_settings.mcp_board_doc_path,
            "mcp_tool_count": len(mcp_client.registry.semantic_map),
        }
        if app_settings.llm_validate_model_on_health:
            checks["llm_model"] = await api.state.intent_service.check_llm_model()

        return HealthResponse(
            status="ok",
            service=app_settings.service_name,
            model=app_settings.llm_model or "not_configured",
            langfuse_enabled=api.state.tracer.enabled,
            mcp_loaded=mcp_client.mcp_loaded,
            checks=checks,
        )

    @api.post("/agent/invoke", response_model=AgentInvokeResponse)
    async def agent_invoke(payload: AgentInvokeRequest) -> AgentInvokeResponse:
        tracer: LangfuseTracer = api.state.tracer
        trace = tracer.start_trace(
            name="agent.invoke",
            session_id=payload.conversation_id,
            user_id=payload.user_id,
            metadata={
                "channel": payload.channel,
                "project_id": payload.metadata.get("project_id"),
            },
            input_payload=payload.model_dump(),
        )
        try:
            result = await api.state.invoke_graph.ainvoke(
                {
                    "conversation_id": payload.conversation_id,
                    "user_id": payload.user_id,
                    "channel": payload.channel,
                    "message": payload.message,
                    "request_metadata": payload.metadata,
                    "trace_id": trace.trace_id,
                    "_trace": trace,
                }
            )
            action = result.get("action")
            final_message = result.get("final_message") or ResponseService.error_response()
            response = AgentInvokeResponse(
                intent=result.get("intent", Intent.UNKNOWN),
                message=final_message,
                requires_confirmation=bool(result.get("requires_confirmation")),
                pending_action_id=result.get("pending_action_id"),
                action=AgentAction.model_validate(action) if action else None,
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response
        except Exception:
            logger.exception("Unhandled error in /agent/invoke")
            response = AgentInvokeResponse(
                intent=Intent.UNKNOWN,
                message=ResponseService.error_response(),
                requires_confirmation=False,
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response

    @api.post("/agent/process", response_model=ExternalAgentProcessResponse)
    async def agent_process(payload: ExternalAgentProcessRequest) -> ExternalAgentProcessResponse:
        """Compatibility endpoint for the existing PMO Agent ExternalAgentService contract."""
        tracer: LangfuseTracer = api.state.tracer
        trace = tracer.start_trace(
            name="agent.process",
            session_id=payload.conversation_id,
            user_id=payload.user_id or "unknown",
            metadata={
                "compatibility": "external_agent_service",
                "project_id": payload.context.get("project_id") or payload.context.get("projectId"),
            },
            input_payload=payload.model_dump(),
        )
        try:
            classification = await api.state.intent_service.classify(payload.input_text)
            entities = {}
            if classification.intent in {
                Intent.TASK_CREATE,
                Intent.TASK_UPDATE,
                Intent.TASK_MOVE,
                Intent.TASK_COMMENT,
            }:
                extracted = await api.state.intent_service.extract_entities(
                    payload.input_text,
                    classification.intent,
                )
                entities = extracted.model_dump(exclude_none=True)
            response = _build_external_agent_response(
                intent=classification.intent,
                confidence=classification.confidence,
                entities=entities,
                context=payload.context,
                input_text=payload.input_text,
            )
            tracer.update_trace(
                trace,
                metadata={
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "compatibility": "external_agent_service",
                },
                output=response.model_dump(mode="json"),
            )
            return response
        except Exception:
            logger.exception("Unhandled error in /agent/process")
            response = ExternalAgentProcessResponse(
                intent="unknown",
                confidence=0.0,
                requires_confirmation=False,
                response_text=ResponseService.error_response(),
                board_action=ExternalBoardAction(type="unknown", payload={}),
                missing_fields=[],
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response

    @api.post("/agent/confirm", response_model=AgentConfirmResponse)
    async def agent_confirm(payload: AgentConfirmRequest) -> AgentConfirmResponse:
        tracer: LangfuseTracer = api.state.tracer
        trace = tracer.start_trace(
            name="agent.confirm",
            session_id=payload.conversation_id,
            user_id=payload.user_id,
            metadata={"confirmed": payload.confirmed},
            input_payload=payload.model_dump(),
        )
        try:
            result = await api.state.confirm_graph.ainvoke(
                {
                    "conversation_id": payload.conversation_id,
                    "user_id": payload.user_id,
                    "pending_action_id": payload.pending_action_id,
                    "confirmed": payload.confirmed,
                    "trace_id": trace.trace_id,
                    "_trace": trace,
                }
            )
            response = AgentConfirmResponse(
                message=result.get("final_message") or ResponseService.error_response(),
                executed=bool(result.get("executed")),
                board_result=result.get("board_result"),
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response
        except Exception:
            logger.exception("Unhandled error in /agent/confirm")
            response = AgentConfirmResponse(
                message=ResponseService.error_response(),
                executed=False,
                board_result=None,
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response

    return api


app = create_app()


def _build_external_agent_response(
    *,
    intent: Intent,
    confidence: float,
    entities: dict[str, Any],
    context: dict[str, Any],
    input_text: str,
) -> ExternalAgentProcessResponse:
    legacy_intent = LEGACY_INTENT_BY_INTENT.get(intent, "unknown")
    action_type = _legacy_action_type(intent, input_text)
    missing_fields = _legacy_missing_fields(intent, entities)
    payload = _legacy_payload(intent, entities, context, input_text)

    requires_confirmation = intent in {
        Intent.TASK_CREATE,
        Intent.TASK_UPDATE,
        Intent.TASK_MOVE,
        Intent.TASK_COMMENT,
    } and not missing_fields

    return ExternalAgentProcessResponse(
        intent=legacy_intent,
        confidence=confidence,
        requires_confirmation=requires_confirmation,
        response_text=_legacy_response_text(intent, missing_fields),
        board_action=ExternalBoardAction(type=action_type, payload=payload),
        missing_fields=missing_fields,
    )


def _legacy_action_type(intent: Intent, input_text: str) -> str:
    text = input_text.casefold()
    if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION} and (
        "alerta" in text or "atras" in text or "bloque" in text
    ):
        return "query_alerts"
    return LEGACY_ACTION_BY_INTENT.get(intent, "unknown")


def _legacy_missing_fields(intent: Intent, entities: dict[str, Any]) -> list[str]:
    missing = []
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
    return missing


def _legacy_payload(
    intent: Intent,
    entities: dict[str, Any],
    context: dict[str, Any],
    input_text: str,
) -> dict[str, Any]:
    project_id = context.get("project_id") or context.get("projectId")

    if intent == Intent.TASK_CREATE:
        return _drop_none(
            {
                "title": entities.get("title"),
                "description": entities.get("description") or entities.get("title"),
                "status": normalize_status(entities.get("status")) if entities.get("status") else None,
                "priority": normalize_priority(entities.get("priority")) if entities.get("priority") else None,
                "assigneeName": entities.get("assignee"),
                "dueDate": entities.get("due_date"),
                "projectId": project_id,
            }
        )

    if intent == Intent.TASK_UPDATE:
        fields = entities.get("fields") or {}
        normalized_fields = {
            key: normalize_priority(value) if key == "priority" else normalize_status(value) if key == "status" else value
            for key, value in fields.items()
        }
        return _drop_none(
            {
                "taskId": entities.get("task_id"),
                "taskQuery": entities.get("task_query"),
                "fields": normalized_fields,
                "projectId": project_id,
            }
        )

    if intent == Intent.TASK_MOVE:
        return _drop_none(
            {
                "taskId": entities.get("task_id"),
                "taskQuery": entities.get("task_query"),
                "status": normalize_status(entities.get("status")) if entities.get("status") else None,
                "projectId": project_id,
            }
        )

    if intent == Intent.TASK_COMMENT:
        return _drop_none(
            {
                "taskId": entities.get("task_id"),
                "taskQuery": entities.get("task_query"),
                "comment": entities.get("comment"),
                "projectId": project_id,
            }
        )

    if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION}:
        return _drop_none({"query": input_text, "projectId": project_id})

    return {}


def _legacy_response_text(intent: Intent, missing_fields: list[str]) -> str:
    if missing_fields:
        if "title" in missing_fields:
            return "Qual e o titulo da atividade?"
        if "task" in missing_fields:
            return "Qual atividade voce quer alterar? Envie o ID ou o titulo."
        if "status" in missing_fields:
            return "Para qual status voce quer mover essa atividade?"
        if "comment" in missing_fields:
            return "Qual comentario voce quer adicionar?"
        if "fields" in missing_fields:
            return "O que voce quer atualizar nessa atividade?"
        return "Preciso de mais detalhes para continuar."

    if intent == Intent.TASK_CREATE:
        return "Confirma a criacao da atividade?"
    if intent == Intent.TASK_UPDATE:
        return "Confirma a atualizacao da atividade?"
    if intent == Intent.TASK_MOVE:
        return "Confirma a movimentacao da atividade?"
    if intent == Intent.TASK_COMMENT:
        return "Confirma a inclusao do comentario?"
    if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION}:
        return "Vou consultar as atividades do board."
    if intent == Intent.SMALLTALK:
        return "Posso ajudar com status, criacao ou atualizacao de atividades."
    return "Nao entendi bem. Pode reformular?"


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}

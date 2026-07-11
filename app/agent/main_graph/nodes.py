from __future__ import annotations

from typing import Any

from app.agent.main_graph.routing import global_command, infer_menu_from_text
from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import inline_keyboard, ui_none
from app.agent.subgraphs.confirmation.nodes import ConfirmationSubgraph
from app.agent.subgraphs.questions.nodes import QuestionsSubgraph
from app.agent.subgraphs.status.nodes import StatusSubgraph
from app.agent.subgraphs.task_create.nodes import CreateTaskSubgraph
from app.agent.subgraphs.task_update.nodes import UpdateTaskSubgraph
from app.agent.subgraphs.welcome.nodes import WelcomeMenuSubgraph
from app.application.memory_service import MemoryService
from app.config import Settings


class PMOMainGraphNodes:
    def __init__(
        self,
        *,
        settings: Settings,
        memory: MemoryService,
        welcome: WelcomeMenuSubgraph,
        status: StatusSubgraph,
        create_task: CreateTaskSubgraph,
        update_task: UpdateTaskSubgraph,
        questions: QuestionsSubgraph,
        confirmation: ConfirmationSubgraph,
    ):
        self.settings = settings
        self.memory = memory
        self.welcome = welcome
        self.status = status
        self.create_task = create_task
        self.update_task = update_task
        self.questions = questions
        self.confirmation = confirmation

    async def validate_event(self, state: PMOAgentState) -> PMOAgentState:
        text = state.get("message_text") or ""
        if len(text) > self.settings.agent_max_message_chars:
            return {
                "current_flow": state.get("current_flow") or "unknown",
                "current_step": "payload_too_large",
                "final_message": "A mensagem excede o tamanho permitido.",
                "response_ui": ui_none(),
                "response_status": "validation_error",
                "error_code": "MESSAGE_TOO_LARGE",
                "error_message": "Message exceeds AGENT_MAX_MESSAGE_CHARS",
                "route": "response_ready",
            }
        return {}

    async def load_identity(self, state: PMOAgentState) -> PMOAgentState:
        return {
            "user_roles": state.get("user_roles") or [],
            "metadata": state.get("metadata") or {},
            "response_status": state.get("response_status") or "completed",
            "response_data": state.get("response_data") or {},
            "requires_confirmation": bool(state.get("requires_confirmation")),
        }

    async def load_thread_memory(self, state: PMOAgentState) -> PMOAgentState:
        if state.get("message_type") == "reset":
            return {}
        thread = await self.memory.load_thread(tenant_id=state["tenant_id"], thread_id=state["thread_id"])
        if not thread:
            return {}
        summary = thread.get("state_summary") or {}
        return {
            "current_flow": summary.get("current_flow") or thread.get("current_flow"),
            "current_step": summary.get("current_step") or thread.get("current_step"),
            "previous_flow": summary.get("previous_flow"),
            "previous_step": summary.get("previous_step"),
            "selected_menu": summary.get("selected_menu"),
            "selected_task_id": summary.get("selected_task_id"),
            "selected_task_number": summary.get("selected_task_number"),
            "task_selection_map": summary.get("task_selection_map") or {},
            "create_draft": summary.get("create_draft") or {},
            "update_draft": summary.get("update_draft") or {},
            "pending_action_id": summary.get("pending_action_id"),
        }

    async def normalize_event(self, state: PMOAgentState) -> PMOAgentState:
        return {
            "message_text": (state.get("message_text") or "").strip() or None,
            "callback_data": (state.get("callback_data") or "").strip() or None,
        }

    async def handle_global_commands(self, state: PMOAgentState) -> PMOAgentState:
        command = global_command(state)
        if not command:
            return {}
        if command == "reset":
            await self.memory.reset_thread(tenant_id=state["tenant_id"], thread_id=state["thread_id"])
            return {"route": "welcome"}
        if command == "menu":
            return {"route": "welcome"}
        if command == "back":
            previous_flow = state.get("previous_flow")
            if previous_flow in {"status", "task_create", "task_update", "questions"}:
                return {"route": previous_flow}
            return {"route": "welcome"}
        return {
            "current_flow": "main_menu",
            "current_step": "waiting_menu_selection",
            "pending_action_id": None,
            "final_message": "Fluxo cancelado. Nenhuma altera\u00e7\u00e3o foi realizada.",
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
            ),
            "response_status": "cancelled",
            "requires_confirmation": False,
            "route": "response_ready",
        }

    async def resolve_current_flow(self, state: PMOAgentState) -> PMOAgentState:
        if state.get("route"):
            return {}
        message_type = state.get("message_type")
        callback = state.get("callback_data") or ""
        if message_type == "welcome":
            return {"route": "welcome"}
        if callback.startswith("confirmation:") or message_type == "confirmation" or state.get("current_flow") == "confirmation":
            return {"route": "confirmation"}
        menu_route = _route_from_menu_callback(callback)
        if menu_route:
            return {
                "selected_menu": menu_route,
                "previous_flow": state.get("current_flow"),
                "previous_step": state.get("current_step"),
                "route": menu_route,
            }
        if callback.startswith("status:") or state.get("current_flow") == "status":
            return {"route": "status"}
        if callback.startswith("update:") or state.get("current_flow") == "task_update":
            return {"route": "task_update"}
        if callback.startswith("create:") or state.get("current_flow") == "task_create":
            return {"route": "task_create"}
        inferred = infer_menu_from_text(state.get("message_text"))
        if inferred:
            return {"selected_menu": inferred, "route": inferred}
        return {"route": "welcome"}

    async def route_to_subgraph(self, state: PMOAgentState) -> PMOAgentState:
        if state.get("route") == "response_ready":
            return {}
        route = state.get("route") or "welcome"
        if route == "welcome":
            return await self.welcome.handle(state)
        if route == "status":
            return await self.status.handle(state)
        if route == "create":
            return await self.create_task.handle({**state, "current_flow": "task_create"})
        if route == "task_create":
            return await self.create_task.handle(state)
        if route == "update":
            return await self.update_task.handle({**state, "current_flow": "task_update"})
        if route == "task_update":
            return await self.update_task.handle(state)
        if route == "questions":
            return await self.questions.handle(state)
        if route == "confirmation":
            return await self.confirmation.handle(state)
        return await self.welcome.handle(state)

    async def persist_session_summary(self, state: PMOAgentState) -> PMOAgentState:
        summary = {
            "current_flow": state.get("current_flow") or "main_menu",
            "current_step": state.get("current_step") or "waiting_menu_selection",
            "previous_flow": state.get("previous_flow"),
            "previous_step": state.get("previous_step"),
            "selected_menu": state.get("selected_menu"),
            "selected_task_id": state.get("selected_task_id"),
            "selected_task_number": state.get("selected_task_number"),
            "task_selection_map": state.get("task_selection_map") or {},
            "create_draft": state.get("create_draft") or {},
            "update_draft": state.get("update_draft") or {},
            "pending_action_id": state.get("pending_action_id"),
        }
        await self.memory.persist_thread(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            channel=state["channel"],
            user_id=state["user_id"],
            user_name=state.get("user_name"),
            current_flow=summary["current_flow"],
            current_step=summary["current_step"],
            state_summary=summary,
            last_event_id=state.get("event_id"),
        )
        return {}

    async def build_api_response(self, state: PMOAgentState) -> PMOAgentState:
        status = state.get("response_status") or "completed"
        response = {
            "request_id": state["request_id"],
            "correlation_id": state["correlation_id"],
            "thread_id": state["thread_id"],
            "status": status,
            "flow": state.get("current_flow") or "main_menu",
            "step": state.get("current_step") or "waiting_menu_selection",
            "message": state.get("final_message") or "Solicita\u00e7\u00e3o processada.",
            "ui": state.get("response_ui") or ui_none(),
            "data": state.get("response_data") or {},
            "requires_confirmation": bool(state.get("requires_confirmation")),
            "confirmation": state.get("confirmation"),
            "error": _error_payload(state),
        }
        return {"api_response": response}


def _route_from_menu_callback(callback: str) -> str | None:
    return {
        "menu:status": "status",
        "menu:create": "create",
        "menu:update": "update",
        "menu:questions": "questions",
    }.get(callback)


def _error_payload(state: PMOAgentState) -> dict[str, Any] | None:
    if not state.get("error_code"):
        return None
    return {
        "code": state.get("error_code"),
        "message": state.get("error_message") or state.get("final_message") or "Erro no agente.",
    }

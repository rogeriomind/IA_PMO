from __future__ import annotations

from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import inline_keyboard
from app.application.confirmation_service import (
    AgentConfirmationService,
    is_approval_text,
    is_rejection_text,
)
from app.application.draft_service import DraftService
from app.storage.repository import PendingActionRepository


class ConfirmationSubgraph:
    def __init__(
        self,
        *,
        confirmations: AgentConfirmationService,
        drafts: DraftService,
        repository: PendingActionRepository,
    ):
        self.confirmations = confirmations
        self.drafts = drafts
        self.repository = repository

    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        callback = state.get("callback_data") or ""
        action, confirmation_id = _callback_action(callback)
        confirmation_id = confirmation_id or state.get("pending_action_id")
        text = state.get("message_text")

        if action == "edit":
            return await self._edit(state, confirmation_id)
        if action == "reject" or (action is None and is_rejection_text(text)):
            if not confirmation_id:
                return self._missing_confirmation(state)
            result = await self.confirmations.reject(
                pending_action_id=confirmation_id,
                tenant_id=state["tenant_id"],
                thread_id=state["thread_id"],
                user_id=state["user_id"],
            )
            return self._result_state(state, result, status_override="cancelled")
        if action == "approve" or (action is None and is_approval_text(text)):
            if not confirmation_id:
                return self._missing_confirmation(state)
            result = await self.confirmations.approve_and_execute(
                pending_action_id=confirmation_id,
                tenant_id=state["tenant_id"],
                thread_id=state["thread_id"],
                user_id=state["user_id"],
                user_roles=state.get("user_roles") or [],
            )
            await self._clear_completed_draft(state, result)
            return self._result_state(state, result)

        return {
            "current_flow": "confirmation",
            "current_step": "awaiting_confirmation",
            "pending_action_id": confirmation_id,
            "final_message": "Preciso de uma confirma\u00e7\u00e3o expl\u00edcita para executar: confirmar ou cancelar.",
            "response_ui": inline_keyboard(
                [
                    {
                        "id": "confirmation_approve",
                        "label": "Confirmar",
                        "callback_data": f"confirmation:approve:{confirmation_id}",
                    },
                    {
                        "id": "confirmation_reject",
                        "label": "Cancelar",
                        "callback_data": f"confirmation:reject:{confirmation_id}",
                    },
                ]
            ),
            "response_status": "awaiting_confirmation",
            "requires_confirmation": True,
        }

    async def _edit(self, state: PMOAgentState, confirmation_id: str | None) -> PMOAgentState:
        pending = self.repository.get_pending_action(confirmation_id) if confirmation_id else None
        action_type = (pending or {}).get("action_type")
        if action_type == "task.create":
            return {
                "current_flow": "task_create",
                "current_step": "waiting_create_details",
                "pending_action_id": None,
                "final_message": "Envie as informa\u00e7\u00f5es corrigidas da atividade.",
                "response_ui": inline_keyboard(
                    [{"id": "global_cancel", "label": "Cancelar", "callback_data": "global:cancel"}]
                ),
                "response_status": "waiting_user_input",
                "requires_confirmation": False,
            }
        if action_type == "task.update":
            return {
                "current_flow": "task_update",
                "current_step": "waiting_update_fields",
                "pending_action_id": None,
                "final_message": "Envie as altera\u00e7\u00f5es corrigidas para a atividade.",
                "response_ui": inline_keyboard(
                    [{"id": "global_cancel", "label": "Cancelar", "callback_data": "global:cancel"}]
                ),
                "response_status": "waiting_user_input",
                "requires_confirmation": False,
            }
        return self._missing_confirmation(state)

    def _missing_confirmation(self, state: PMOAgentState) -> PMOAgentState:
        return {
            "current_flow": "confirmation",
            "current_step": "confirmation_not_found",
            "final_message": "N\u00e3o encontrei uma confirma\u00e7\u00e3o pendente para esta conversa.",
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
            ),
            "response_status": "not_found",
            "error_code": "CONFIRMATION_NOT_FOUND",
        }

    async def _clear_completed_draft(self, state: PMOAgentState, result: dict) -> None:
        if result.get("status") not in {"completed", "degraded"}:
            return
        pending_id = state.get("pending_action_id")
        pending = self.repository.get_pending_action(pending_id) if pending_id else None
        draft_type = "task_create" if (pending or {}).get("action_type") == "task.create" else "task_update"
        await self.drafts.clear(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type=draft_type,
        )

    def _result_state(
        self,
        state: PMOAgentState,
        result: dict,
        *,
        status_override: str | None = None,
    ) -> PMOAgentState:
        status = status_override or result.get("status") or "completed"
        return {
            "current_flow": "main_menu" if status in {"completed", "cancelled"} else "confirmation",
            "current_step": "waiting_menu_selection" if status in {"completed", "cancelled"} else "confirmation_error",
            "pending_action_id": None if status in {"completed", "cancelled"} else state.get("pending_action_id"),
            "confirmation_status": result.get("confirmation_status"),
            "final_message": result.get("message") or "Solicita\u00e7\u00e3o processada.",
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
            ),
            "response_status": status,
            "response_data": result.get("data") or {},
            "requires_confirmation": False,
            "error_code": result.get("error_code"),
        }


def _callback_action(callback: str) -> tuple[str | None, str | None]:
    if not callback.startswith("confirmation:"):
        return None, None
    parts = callback.split(":")
    if len(parts) < 3:
        return None, None
    return parts[1], parts[2]

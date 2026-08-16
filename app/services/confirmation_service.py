from __future__ import annotations

from typing import Any

from app.infrastructure.observability.metrics import AgentMetrics
from app.mcp.board_tools import BoardTools
from app.schemas import PendingActionStatus
from app.services.pending_action_service import PendingActionService


class ConfirmationService:
    def __init__(
        self,
        pending_actions: PendingActionService,
        board_tools: BoardTools,
        *,
        metrics: AgentMetrics | None = None,
    ):
        self.pending_actions = pending_actions
        self.board_tools = board_tools
        self.metrics = metrics

    async def confirm_and_execute(
        self,
        *,
        pending_action_id: str,
        conversation_id: str,
        user_id: str,
        confirmed: bool,
    ) -> tuple[bool, Any, str]:
        pending = self.pending_actions.get(pending_action_id)
        if not pending:
            return False, None, "Nao encontrei essa acao pendente. Ela pode ter expirado ou ja ter sido concluida."

        if pending["conversation_id"] != conversation_id or pending["user_id"] != user_id:
            return False, None, "Essa confirmacao nao corresponde a conversa original da acao."

        if pending["status"] != PendingActionStatus.PENDING.value:
            return False, pending.get("result"), "Essa acao nao esta mais pendente."

        if not confirmed:
            self.pending_actions.mark_cancelled(pending_action_id)
            return False, None, "Ok, acao cancelada. Nada foi alterado no board."

        self.pending_actions.mark_confirmed(pending_action_id)
        try:
            result = await self._execute(pending)
            self.pending_actions.mark_executed(pending_action_id, result)
            return True, result, self._success_message(pending["action_type"])
        except Exception as exc:
            self.pending_actions.mark_failed(pending_action_id, str(exc))
            return False, None, "Nao consegui executar a acao no board agora. Tente novamente em instantes."

    async def _execute(self, pending: dict[str, Any]) -> Any:
        action_type = pending["action_type"]
        payload = pending["action_payload"] or {}
        idempotency_key = pending["id"]
        self._record_legacy_mcp_call()

        if action_type == "create_task":
            return await self.board_tools.create_task(payload, idempotency_key=idempotency_key)
        if action_type == "update_task":
            return await self.board_tools.update_task(
                task_id=payload.get("task_id"),
                fields=payload.get("fields", {}),
                task_query=payload.get("task_query"),
                idempotency_key=idempotency_key,
            )
        if action_type == "move_task":
            return await self.board_tools.move_task(
                task_id=payload.get("task_id"),
                status=payload.get("status"),
                task_query=payload.get("task_query"),
                idempotency_key=idempotency_key,
            )
        if action_type == "add_comment":
            return await self.board_tools.add_comment(
                task_id=payload.get("task_id"),
                comment=payload.get("comment"),
                task_query=payload.get("task_query"),
                idempotency_key=idempotency_key,
            )
        raise ValueError(f"Unsupported action type: {action_type}")

    def _record_legacy_mcp_call(self) -> None:
        if self.metrics:
            self.metrics.increment("mcp_calls_total", api_version="legacy")
            self.metrics.increment("agent_mcp_calls_total", api_version="legacy")

    @staticmethod
    def _success_message(action_type: str) -> str:
        return {
            "create_task": "Tarefa criada com sucesso no board.",
            "update_task": "Tarefa atualizada com sucesso no board.",
            "move_task": "Tarefa movida com sucesso no board.",
            "add_comment": "Comentario adicionado com sucesso no board.",
        }.get(action_type, "Acao executada com sucesso no board.")

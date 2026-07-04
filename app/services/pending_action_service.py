from __future__ import annotations

from typing import Any

from app.schemas import Intent
from app.storage.repository import PendingActionRepository


ACTION_TYPE_BY_INTENT = {
    Intent.TASK_CREATE: "create_task",
    Intent.TASK_UPDATE: "update_task",
    Intent.TASK_MOVE: "move_task",
    Intent.TASK_COMMENT: "add_comment",
}


class PendingActionService:
    def __init__(self, repository: PendingActionRepository):
        self.repository = repository

    def create_from_intent(
        self,
        *,
        conversation_id: str,
        user_id: str,
        intent: Intent,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        action_type = ACTION_TYPE_BY_INTENT[intent]
        return self.repository.create_pending_action(
            conversation_id=conversation_id,
            user_id=user_id,
            action_type=action_type,
            action_payload=payload,
        )

    def get(self, pending_action_id: str) -> dict[str, Any] | None:
        return self.repository.get_pending_action(pending_action_id)

    def mark_confirmed(self, pending_action_id: str) -> dict[str, Any] | None:
        return self.repository.mark_confirmed(pending_action_id)

    def mark_cancelled(self, pending_action_id: str) -> dict[str, Any] | None:
        return self.repository.mark_cancelled(pending_action_id)

    def mark_executed(self, pending_action_id: str, result: Any) -> dict[str, Any] | None:
        return self.repository.mark_executed(pending_action_id, result)

    def mark_failed(self, pending_action_id: str, error: str, result: Any | None = None) -> dict[str, Any] | None:
        return self.repository.mark_failed(pending_action_id, error, result)


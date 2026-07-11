from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.config import Settings
from app.storage.repository import PendingActionRepository, utcnow


class TaskSelectionService:
    def __init__(self, repository: PendingActionRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    async def replace_map(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        context: str,
        tasks: list[dict[str, Any]],
    ) -> dict[str, str]:
        expires_at = utcnow() + timedelta(minutes=self.settings.agent_task_selection_ttl_minutes)
        items = [
            {
                "selection_number": index,
                "task_id": str(task.get("id") or task.get("task_id")),
                "task_title": task.get("title") or task.get("name"),
            }
            for index, task in enumerate(tasks, start=1)
            if task.get("id") or task.get("task_id")
        ]
        self.repository.replace_task_selection_map(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            context=context,
            items=items,
            expires_at=expires_at,
        )
        return {str(item["selection_number"]): item["task_id"] for item in items}

    async def resolve(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        context: str,
        selection_number: int,
    ) -> dict[str, Any] | None:
        return self.repository.resolve_task_selection(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            context=context,
            selection_number=selection_number,
        )

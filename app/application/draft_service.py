from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.config import Settings
from app.storage.repository import PendingActionRepository, utcnow


class DraftService:
    def __init__(self, repository: PendingActionRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    async def get(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        draft_type: str,
    ) -> dict[str, Any] | None:
        return self.repository.get_active_draft(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            draft_type=draft_type,
        )

    async def save(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        draft_type: str,
        payload: dict[str, Any],
        status: str = "active",
    ) -> dict[str, Any]:
        expires_at = utcnow() + timedelta(minutes=self.settings.agent_session_ttl_minutes)
        return self.repository.upsert_draft(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            draft_type=draft_type,
            payload=payload,
            status=status,
            expires_at=expires_at,
        )

    async def clear(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        draft_type: str,
    ) -> None:
        self.repository.clear_draft(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            draft_type=draft_type,
        )

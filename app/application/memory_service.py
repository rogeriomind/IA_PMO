from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.config import Settings
from app.storage.repository import PendingActionRepository, utcnow


class MemoryService:
    def __init__(self, repository: PendingActionRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    async def load_thread(self, *, tenant_id: str, thread_id: str) -> dict[str, Any] | None:
        return self.repository.get_agent_thread(tenant_id=tenant_id, thread_id=thread_id)

    async def persist_thread(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        channel: str,
        user_id: str,
        user_name: str | None,
        current_flow: str,
        current_step: str,
        state_summary: dict[str, Any],
        last_event_id: str | None,
    ) -> dict[str, Any]:
        expires_at = utcnow() + timedelta(minutes=self.settings.agent_session_ttl_minutes)
        return self.repository.upsert_agent_thread(
            tenant_id=tenant_id,
            thread_id=thread_id,
            channel=channel,
            user_id=user_id,
            user_name=user_name,
            current_flow=current_flow,
            current_step=current_step,
            state_summary=state_summary,
            last_event_id=last_event_id,
            expires_at=expires_at,
        )

    async def reset_thread(self, *, tenant_id: str, thread_id: str) -> None:
        self.repository.reset_agent_thread(tenant_id=tenant_id, thread_id=thread_id)

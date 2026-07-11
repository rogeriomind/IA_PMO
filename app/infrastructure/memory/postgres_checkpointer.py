from __future__ import annotations

from typing import Any

from app.storage.repository import PendingActionRepository


class PostgresAgentCheckpointer:
    """Async facade for persisted LangGraph-compatible conversation checkpoints."""

    def __init__(self, repository: PendingActionRepository):
        self.repository = repository

    async def aput(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        checkpoint: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.repository.upsert_graph_checkpoint(
            tenant_id=tenant_id,
            thread_id=thread_id,
            checkpoint=checkpoint,
            metadata_json=metadata or {},
        )

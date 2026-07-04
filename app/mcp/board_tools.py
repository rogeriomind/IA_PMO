from __future__ import annotations

from typing import Any

from app.mcp.client import MCPBoardClient


PRIORITY_MAP = {
    "LOW": "LOW",
    "BAIXA": "LOW",
    "LOW_PRIORITY": "LOW",
    "MEDIUM": "MEDIUM",
    "MEDIA": "MEDIUM",
    "MÉDIA": "MEDIUM",
    "NORMAL": "MEDIUM",
    "HIGH": "HIGH",
    "ALTA": "HIGH",
    "URGENTE": "CRITICAL",
    "CRITICAL": "CRITICAL",
    "CRITICA": "CRITICAL",
    "CRÍTICA": "CRITICAL",
}

STATUS_MAP = {
    "TODO": "TODO",
    "A FAZER": "TODO",
    "BACKLOG": "TODO",
    "IN_PROGRESS": "IN_PROGRESS",
    "EM ANDAMENTO": "IN_PROGRESS",
    "ANDAMENTO": "IN_PROGRESS",
    "REVIEW": "REVIEW",
    "REVISAO": "REVIEW",
    "REVISÃO": "REVIEW",
    "DONE": "DONE",
    "CONCLUIDO": "DONE",
    "CONCLUÍDO": "DONE",
    "FEITO": "DONE",
    "BLOCKED": "BLOCKED",
    "BLOQUEADO": "BLOCKED",
}


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def normalize_priority(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    key = value.strip().upper().replace("-", "_")
    return PRIORITY_MAP.get(key, value)


def normalize_status(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    key = value.strip().upper().replace("-", "_")
    return STATUS_MAP.get(key, value)


def normalize_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "priority" in normalized:
        normalized["priority"] = normalize_priority(normalized["priority"])
    if "status" in normalized:
        normalized["status"] = normalize_status(normalized["status"])
    fields = normalized.get("fields")
    if isinstance(fields, dict):
        normalized["fields"] = normalize_task_payload(fields)
    return normalized


class BoardTools:
    def __init__(self, client: MCPBoardClient):
        self.client = client

    async def search_tasks(self, query: str, project_id: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "search_tasks",
            drop_none({"query": query, "project_id": project_id}),
            read_only=True,
        )

    async def get_task(self, task_id: str) -> Any:
        return await self.client.call_semantic_tool("get_task", {"task_id": task_id}, read_only=True)

    async def create_task(self, payload: dict[str, Any], idempotency_key: str | None = None) -> Any:
        arguments = drop_none({**normalize_task_payload(payload), "idempotency_key": idempotency_key})
        return await self.client.call_semantic_tool("create_task", arguments, read_only=False)

    async def update_task(
        self,
        *,
        task_id: str | None,
        fields: dict[str, Any],
        task_query: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        arguments = drop_none(
            {
                "task_id": task_id,
                "task_query": task_query,
                "fields": normalize_task_payload(fields),
                "idempotency_key": idempotency_key,
            }
        )
        return await self.client.call_semantic_tool("update_task", arguments, read_only=False)

    async def move_task(
        self,
        *,
        task_id: str | None,
        status: str | None,
        task_query: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        arguments = drop_none(
            {
                "task_id": task_id,
                "task_query": task_query,
                "status": normalize_status(status),
                "idempotency_key": idempotency_key,
            }
        )
        return await self.client.call_semantic_tool("move_task", arguments, read_only=False)

    async def add_comment(
        self,
        *,
        task_id: str | None,
        comment: str | None,
        task_query: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        arguments = drop_none(
            {
                "task_id": task_id,
                "task_query": task_query,
                "comment": comment,
                "idempotency_key": idempotency_key,
            }
        )
        return await self.client.call_semantic_tool("add_comment", arguments, read_only=False)

    async def get_project_status(self, project_id: str | None = None, query: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "get_project_status",
            drop_none({"project_id": project_id, "query": query}),
            read_only=True,
        )

    async def list_blockers(self, project_id: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "list_blockers",
            drop_none({"project_id": project_id}),
            read_only=True,
        )

    async def list_my_tasks(self, user_id: str, project_id: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "list_my_tasks",
            drop_none({"user_id": user_id, "project_id": project_id}),
            read_only=True,
        )

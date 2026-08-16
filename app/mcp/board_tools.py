from __future__ import annotations

import re
import unicodedata
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
    "BACKLOG": "BACKLOG",
    "IN_PROGRESS": "IN_PROGRESS",
    "EM ANDAMENTO": "IN_PROGRESS",
    "ANDAMENTO": "IN_PROGRESS",
    "REVIEW": "IN_REVIEW",
    "IN_REVIEW": "IN_REVIEW",
    "REVISAO": "IN_REVIEW",
    "REVISÃO": "IN_REVIEW",
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
    plain_key = unicodedata.normalize("NFKD", key)
    plain_key = "".join(char for char in plain_key if not unicodedata.combining(char))
    return STATUS_MAP.get(key) or STATUS_MAP.get(plain_key, value)


def normalize_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "due_date" in normalized:
        normalized["dueDate"] = normalized.pop("due_date")
    if "assignee_id" in normalized:
        value = normalized.pop("assignee_id")
        if value is not None:
            normalized["assigneeId"] = value
    if "assignee" in normalized:
        value = normalized.pop("assignee")
        if value is not None:
            normalized["assigneeId"] = value
    if "priority" in normalized:
        normalized["priority"] = normalize_priority(normalized["priority"])
    if "status" in normalized:
        normalized["status"] = normalize_status(normalized["status"])
    fields = normalized.get("fields")
    if isinstance(fields, dict):
        normalized["fields"] = normalize_task_payload(fields)
    return normalized


def _match_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text.casefold()).strip()
    return text


def _extract_tasks(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        tasks = result.get("tasks") or result.get("items") or result.get("data")
        if isinstance(tasks, list):
            return [task for task in tasks if isinstance(task, dict)]
        task = result.get("task")
        if isinstance(task, dict):
            return [task]
    if isinstance(result, list):
        return [task for task in result if isinstance(task, dict)]
    return []


class BoardTools:
    def __init__(self, client: MCPBoardClient, *, read_retries: int | None = None):
        self.client = client
        self.read_retries = read_retries

    async def search_tasks(self, query: str, project_id: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "search_tasks",
            drop_none({"search": query}),
            read_only=True,
            read_retries=self.read_retries,
        )

    async def get_task(self, task_id: str) -> Any:
        return await self.client.call_semantic_tool(
            "get_task",
            {"id": task_id},
            read_only=True,
            read_retries=self.read_retries,
        )

    async def search_users(self, query: str | None = None, limit: int = 20) -> Any:
        return await self.client.call_semantic_tool(
            "search_users",
            drop_none({"query": query, "limit": limit}),
            read_only=True,
            read_retries=self.read_retries,
        )

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
        resolved_task_id = await self._resolve_task_id(task_id=task_id, task_query=task_query)
        arguments = drop_none({"id": resolved_task_id, **normalize_task_payload(fields)})
        return await self.client.call_semantic_tool("update_task", arguments, read_only=False)

    async def move_task(
        self,
        *,
        task_id: str | None,
        status: str | None,
        task_query: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        resolved_task_id = await self._resolve_task_id(task_id=task_id, task_query=task_query)
        arguments = drop_none({"id": resolved_task_id, "status": normalize_status(status)})
        return await self.client.call_semantic_tool("move_task", arguments, read_only=False)

    async def add_comment(
        self,
        *,
        task_id: str | None,
        comment: str | None,
        task_query: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        resolved_task_id = await self._resolve_task_id(task_id=task_id, task_query=task_query)
        arguments = drop_none({"id": resolved_task_id, "message": comment})
        return await self.client.call_semantic_tool("add_comment", arguments, read_only=False)

    async def get_project_status(self, project_id: str | None = None, query: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "get_project_status",
            drop_none({"project_id": project_id, "query": query}),
            read_only=True,
            read_retries=self.read_retries,
        )

    async def list_blockers(self, project_id: str | None = None) -> Any:
        return await self.client.call_semantic_tool(
            "list_blockers",
            drop_none({"project_id": project_id}),
            read_only=True,
            read_retries=self.read_retries,
        )

    async def list_my_tasks(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
        assignee_id: str | None = None,
        assignee_email: str | None = None,
    ) -> Any:
        if not assignee_id and user_id and _looks_like_uuid(user_id):
            assignee_id = user_id
        return await self.client.call_semantic_tool(
            "list_my_tasks",
            drop_none({"assigneeId": assignee_id, "assigneeEmail": assignee_email, "project_id": project_id}),
            read_only=True,
            read_retries=self.read_retries,
        )

    async def _resolve_task_id(self, *, task_id: str | None, task_query: str | None) -> str:
        if task_id:
            return task_id
        if not task_query:
            raise ValueError("Informe task_id ou task_query para localizar a tarefa.")

        result = await self.search_tasks(task_query)
        tasks = _extract_tasks(result)
        if not tasks:
            raise ValueError(f"Nenhuma tarefa encontrada para '{task_query}'.")

        target = _match_text(task_query)
        exact_matches = [task for task in tasks if _match_text(task.get("title")) == target]
        if len(exact_matches) == 1:
            resolved_id = exact_matches[0].get("id")
            if isinstance(resolved_id, str) and resolved_id:
                return resolved_id

        title_matches = [task for task in tasks if target and target in _match_text(task.get("title"))]
        if len(title_matches) == 1:
            resolved_id = title_matches[0].get("id")
            if isinstance(resolved_id, str) and resolved_id:
                return resolved_id

        if len(tasks) == 1:
            resolved_id = tasks[0].get("id")
            if isinstance(resolved_id, str) and resolved_id:
                return resolved_id

        raise ValueError(f"Encontrei mais de uma tarefa para '{task_query}'. Informe o id da tarefa.")


def _looks_like_uuid(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value.strip(),
        )
    )

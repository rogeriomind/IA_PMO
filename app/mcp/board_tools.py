from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
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


CONTEXT_PAYLOAD_KEYS = {
    "tenant_id",
    "tenantId",
    "project_id",
    "projectId",
    "portfolio_id",
    "portfolioId",
    "activity_id",
    "activityId",
    "idempotency_key",
    "idempotencyKey",
    "project",
}


def normalize_write_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_task_payload(payload)
    return {key: value for key, value in normalized.items() if key not in CONTEXT_PAYLOAD_KEYS}


@dataclass(frozen=True)
class SearchProjectsArgs:
    tenant_id: str
    search: str
    limit: int | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "search": self.search,
                "limit": self.limit,
            }
        )


@dataclass(frozen=True)
class SearchUsersArgs:
    tenant_id: str
    query: str | None = None
    limit: int = 20
    project_id: str | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "query": self.query,
                "limit": self.limit,
            }
        )


@dataclass(frozen=True)
class SearchTasksArgs:
    tenant_id: str
    project_id: str
    query: str
    limit: int | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "search": self.query,
                "limit": self.limit,
            }
        )


@dataclass(frozen=True)
class GetTaskArgs:
    tenant_id: str
    project_id: str
    activity_id: str

    def to_mcp_arguments(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "id": self.activity_id,
        }


@dataclass(frozen=True)
class CreateTaskArgs:
    tenant_id: str
    project_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "idempotencyKey": self.idempotency_key,
                **normalize_write_payload(self.payload),
            }
        )


@dataclass(frozen=True)
class UpdateTaskArgs:
    tenant_id: str
    project_id: str
    activity_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "id": self.activity_id,
                "idempotencyKey": self.idempotency_key,
                **normalize_write_payload(self.fields),
            }
        )


@dataclass(frozen=True)
class MoveTaskArgs:
    tenant_id: str
    project_id: str
    activity_id: str
    status: str | None
    idempotency_key: str | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "id": self.activity_id,
                "status": normalize_status(self.status),
                "idempotencyKey": self.idempotency_key,
            }
        )


@dataclass(frozen=True)
class AddCommentArgs:
    tenant_id: str
    project_id: str
    activity_id: str
    comment: str | None
    idempotency_key: str | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "id": self.activity_id,
                "message": self.comment,
                "idempotencyKey": self.idempotency_key,
            }
        )


@dataclass(frozen=True)
class ProjectStatusArgs:
    tenant_id: str
    project_id: str

    def to_mcp_arguments(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
        }


@dataclass(frozen=True)
class ListBlockersArgs:
    tenant_id: str
    project_id: str
    assignee_id: str | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "assigneeId": self.assignee_id,
            }
        )


@dataclass(frozen=True)
class ListMyTasksArgs:
    tenant_id: str
    project_id: str
    assignee_id: str | None = None
    assignee_email: str | None = None
    include_completed: bool | None = None

    def to_mcp_arguments(self) -> dict[str, Any]:
        return drop_none(
            {
                "tenantId": self.tenant_id,
                "projectId": self.project_id,
                "assigneeId": self.assignee_id,
                "assigneeEmail": self.assignee_email,
                "includeCompleted": self.include_completed,
            }
        )


def _match_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text.casefold()).strip()
    return text


def _extract_tasks(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        tasks = result.get("tasks") or result.get("activities") or result.get("items") or result.get("data")
        if isinstance(tasks, list):
            return [task for task in tasks if isinstance(task, dict)]
        task = result.get("task") or result.get("activity")
        if isinstance(task, dict):
            return [task]
    if isinstance(result, list):
        return [task for task in result if isinstance(task, dict)]
    return []


class BoardTools:
    def __init__(self, client: MCPBoardClient, *, read_retries: int | None = None):
        self.client = client
        self.read_retries = read_retries

    async def search_projects(self, *, tenant_id: str, query: str, limit: int | None = 10) -> Any:
        arguments = SearchProjectsArgs(tenant_id=tenant_id, search=query, limit=limit).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "search_projects",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def search_tasks(
        self,
        *,
        tenant_id: str,
        project_id: str,
        query: str,
        limit: int | None = None,
    ) -> Any:
        arguments = SearchTasksArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            query=query,
            limit=limit,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "search_tasks",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def get_task(self, *, tenant_id: str, project_id: str, activity_id: str) -> Any:
        arguments = GetTaskArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=activity_id,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "get_task",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def search_users(
        self,
        *,
        tenant_id: str,
        query: str | None = None,
        limit: int = 20,
        project_id: str | None = None,
    ) -> Any:
        arguments = SearchUsersArgs(
            tenant_id=tenant_id,
            query=query,
            limit=limit,
            project_id=project_id,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "search_users",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def create_task(
        self,
        *,
        tenant_id: str,
        project_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> Any:
        arguments = CreateTaskArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            payload=payload,
            idempotency_key=idempotency_key,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool("create_task", arguments, read_only=False)

    async def update_task(
        self,
        *,
        tenant_id: str,
        project_id: str,
        activity_id: str | None = None,
        task_id: str | None = None,
        fields: dict[str, Any],
        task_query: str | None = None,
        idempotency_key: str,
    ) -> Any:
        resolved_task_id = await self._resolve_task_id(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=activity_id or task_id,
            task_query=task_query,
        )
        arguments = UpdateTaskArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=resolved_task_id,
            fields=fields,
            idempotency_key=idempotency_key,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool("update_task", arguments, read_only=False)

    async def move_task(
        self,
        *,
        tenant_id: str,
        project_id: str,
        activity_id: str | None = None,
        task_id: str | None = None,
        status: str | None,
        task_query: str | None = None,
        idempotency_key: str,
    ) -> Any:
        resolved_task_id = await self._resolve_task_id(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=activity_id or task_id,
            task_query=task_query,
        )
        arguments = MoveTaskArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=resolved_task_id,
            status=status,
            idempotency_key=idempotency_key,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool("move_task", arguments, read_only=False)

    async def add_comment(
        self,
        *,
        tenant_id: str,
        project_id: str,
        activity_id: str | None = None,
        task_id: str | None = None,
        comment: str | None,
        task_query: str | None = None,
        idempotency_key: str,
    ) -> Any:
        resolved_task_id = await self._resolve_task_id(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=activity_id or task_id,
            task_query=task_query,
        )
        arguments = AddCommentArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            activity_id=resolved_task_id,
            comment=comment,
            idempotency_key=idempotency_key,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool("add_comment", arguments, read_only=False)

    async def get_project_status(self, *, tenant_id: str, project_id: str) -> Any:
        arguments = ProjectStatusArgs(tenant_id=tenant_id, project_id=project_id).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "get_project_status",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def list_blockers(
        self,
        *,
        tenant_id: str,
        project_id: str,
        assignee_id: str | None = None,
    ) -> Any:
        arguments = ListBlockersArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            assignee_id=assignee_id,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "list_blockers",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def list_my_tasks(
        self,
        *,
        tenant_id: str,
        project_id: str,
        user_id: str | None = None,
        assignee_id: str | None = None,
        assignee_email: str | None = None,
        include_completed: bool | None = None,
    ) -> Any:
        if not assignee_id and user_id and _looks_like_uuid(user_id):
            assignee_id = user_id
        arguments = ListMyTasksArgs(
            tenant_id=tenant_id,
            project_id=project_id,
            assignee_id=assignee_id,
            assignee_email=assignee_email,
            include_completed=include_completed,
        ).to_mcp_arguments()
        return await self.client.call_semantic_tool(
            "list_my_tasks",
            arguments,
            read_only=True,
            read_retries=self.read_retries,
        )

    async def _resolve_task_id(
        self,
        *,
        tenant_id: str,
        project_id: str,
        activity_id: str | None,
        task_query: str | None,
    ) -> str:
        if activity_id:
            return activity_id
        if not task_query:
            raise ValueError("Informe activity_id ou task_query para localizar a atividade.")

        result = await self.search_tasks(tenant_id=tenant_id, project_id=project_id, query=task_query)
        tasks = _extract_tasks(result)
        if not tasks:
            raise ValueError(f"Nenhuma atividade encontrada para '{task_query}'.")

        target = _match_text(task_query)
        exact_matches = [task for task in tasks if _match_text(task.get("title")) == target]
        if len(exact_matches) == 1:
            resolved_id = exact_matches[0].get("id") or exact_matches[0].get("activityId")
            if isinstance(resolved_id, str) and resolved_id:
                return resolved_id

        title_matches = [task for task in tasks if target and target in _match_text(task.get("title"))]
        if len(title_matches) == 1:
            resolved_id = title_matches[0].get("id") or title_matches[0].get("activityId")
            if isinstance(resolved_id, str) and resolved_id:
                return resolved_id

        if len(tasks) == 1:
            resolved_id = tasks[0].get("id") or tasks[0].get("activityId")
            if isinstance(resolved_id, str) and resolved_id:
                return resolved_id

        raise ValueError(f"Encontrei mais de uma atividade para '{task_query}'. Informe o id da atividade.")


def _looks_like_uuid(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value.strip(),
        )
    )

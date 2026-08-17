from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import time
from dataclasses import replace
from typing import Any, Protocol

from pydantic import ValidationError

from app.agent.context import ToolExecutionContext
from app.agent.errors import (
    AuthorizationError,
    ConfirmationRequiredError,
    IdempotencyConflictError,
    MCPPermanentError,
    MCPTimeoutError,
    MCPTransientError,
    ProjectContextMissingError,
    TenantContextMissingError,
    ToolNotAllowedError,
    ToolValidationError,
)
from app.agent.latency import record_mcp_call
from app.agent.tool_registry import ToolRegistry, ToolSpec
from app.infrastructure.observability.metrics import AgentMetrics
from app.mcp.board_tools import BoardTools
from app.storage.repository import PendingActionRepository

logger = logging.getLogger(__name__)


PROJECT_SCOPED_TOOLS = {
    "board_search_tasks",
    "board_get_task",
    "board_create_task",
    "board_update_task",
    "board_move_task",
    "board_add_comment",
    "board_get_project_status",
    "board_list_blockers",
    "board_list_my_tasks",
}

ACTIVITY_SCOPED_TOOLS = {
    "board_get_task",
    "board_update_task",
    "board_move_task",
    "board_add_comment",
}


class MCPExecutor(Protocol):
    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        ...


class BoardToolsExecutor:
    def __init__(self, board_tools: BoardTools):
        self.board_tools = board_tools

    async def _call(self, method_name: str, **kwargs: Any) -> Any:
        method = getattr(self.board_tools, method_name)
        parameters = inspect.signature(method).parameters
        if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
            return await method(**kwargs)
        accepted = {key: value for key, value in kwargs.items() if key in parameters}
        return await method(**accepted)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        tenant_id = arguments.get("tenant_id")
        project_id = arguments.get("project_id")
        activity_id = arguments.get("activity_id")
        if tool_name == "board_search_tasks":
            return await self._call(
                "search_tasks",
                tenant_id=tenant_id,
                project_id=project_id,
                query=arguments.get("search") or arguments.get("query") or "",
                limit=arguments.get("limit"),
            )
        if tool_name == "board_get_task":
            return await self._call(
                "get_task",
                tenant_id=tenant_id,
                project_id=project_id,
                activity_id=activity_id,
                task_id=activity_id,
            )
        if tool_name == "board_search_users":
            return await self._call(
                "search_users",
                tenant_id=tenant_id,
                query=arguments.get("query"),
                limit=arguments.get("limit") or 20,
                project_id=project_id,
            )
        if tool_name == "board_create_task":
            return await self._call(
                "create_task",
                tenant_id=tenant_id,
                project_id=project_id,
                payload=arguments,
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_update_task":
            return await self._call(
                "update_task",
                tenant_id=tenant_id,
                project_id=project_id,
                activity_id=activity_id,
                task_id=activity_id,
                task_query=arguments.get("task_query"),
                fields=arguments.get("fields") or {},
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_move_task":
            return await self._call(
                "move_task",
                tenant_id=tenant_id,
                project_id=project_id,
                activity_id=activity_id,
                task_id=activity_id,
                task_query=arguments.get("task_query"),
                status=arguments.get("status"),
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_add_comment":
            return await self._call(
                "add_comment",
                tenant_id=tenant_id,
                project_id=project_id,
                activity_id=activity_id,
                task_id=activity_id,
                task_query=arguments.get("task_query"),
                comment=arguments.get("comment"),
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_get_project_status":
            return await self._call(
                "get_project_status",
                tenant_id=tenant_id,
                project_id=project_id,
            )
        if tool_name == "board_list_blockers":
            return await self._call(
                "list_blockers",
                tenant_id=tenant_id,
                project_id=project_id,
                assignee_id=arguments.get("assigneeId"),
            )
        if tool_name == "board_list_my_tasks":
            return await self._call(
                "list_my_tasks",
                tenant_id=tenant_id,
                user_id=arguments.get("user_id"),
                project_id=project_id,
                assignee_id=arguments.get("assigneeId"),
                assignee_email=arguments.get("assigneeEmail"),
                include_completed=arguments.get("includeCompleted"),
            )
        raise ToolNotAllowedError(f"Unknown board tool: {tool_name}")


class ToolExecutionResult:
    def __init__(
        self,
        *,
        tool_name: str,
        status: str,
        result: Any | None,
        latency_ms: int,
        idempotency_key: str | None = None,
        from_idempotency: bool = False,
        error_code: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.status = status
        self.result = result
        self.latency_ms = latency_ms
        self.idempotency_key = idempotency_key
        self.from_idempotency = from_idempotency
        self.error_code = error_code

    def model_dump(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "result": self.result,
            "latency_ms": self.latency_ms,
            "idempotency_key": self.idempotency_key,
            "from_idempotency": self.from_idempotency,
            "error_code": self.error_code,
        }


class MCPGateway:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        executor: MCPExecutor,
        repository: PendingActionRepository,
        result_max_chars: int,
        metrics: AgentMetrics | None = None,
    ) -> None:
        self.registry = registry
        self.executor = executor
        self.repository = repository
        self.result_max_chars = result_max_chars
        self.metrics = metrics
        self._failure_counts: dict[str, tuple[int, float]] = {}

    async def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        spec = self._get_allowed_spec(tool_name, context)
        prepared = self._prepare_arguments(spec, arguments, context)
        validated = self._validate_arguments(spec, prepared)
        execution_context = replace(
            context,
            project_id=validated.get("project_id") or context.project_id,
            activity_id=validated.get("activity_id") or context.activity_id,
        )
        self._authorize(spec, execution_context)

        if spec.requires_confirmation and execution_context.approval_status != "approved":
            raise ConfirmationRequiredError()

        if spec.type == "write":
            return await self._execute_write(spec, validated, execution_context)
        return await self._execute_read(spec, validated, execution_context)

    def _get_allowed_spec(self, tool_name: str, context: ToolExecutionContext) -> ToolSpec:
        if not self.registry.has(tool_name):
            raise ToolNotAllowedError(f"Tool not registered: {tool_name}")
        spec = self.registry.get(tool_name)
        if context.intent not in spec.allowed_intents:
            raise ToolNotAllowedError(
                f"Tool {tool_name} is not allowed for intent {context.intent}"
            )
        return spec

    @staticmethod
    def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return spec.input_model.model_validate(arguments).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise ToolValidationError(str(exc)) from exc

    def _prepare_arguments(
        self,
        spec: ToolSpec,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        if not context.tenant_id:
            raise TenantContextMissingError()

        prepared = self._canonicalize_arguments(arguments)
        if spec.name == "board_search_tasks" and not prepared.get("search") and "query" in prepared:
            prepared["search"] = prepared["query"]
        prepared["tenant_id"] = prepared.get("tenant_id") or context.tenant_id

        project_id = prepared.get("project_id") or context.project_id
        if spec.name in PROJECT_SCOPED_TOOLS:
            if not project_id:
                raise ProjectContextMissingError()
            prepared["project_id"] = project_id

        activity_id = prepared.get("activity_id") or context.activity_id
        if spec.name in ACTIVITY_SCOPED_TOOLS and activity_id:
            prepared["activity_id"] = activity_id

        allowed_keys = self._allowed_input_keys(spec)
        return {key: value for key, value in prepared.items() if key in allowed_keys}

    @staticmethod
    def _allowed_input_keys(spec: ToolSpec) -> set[str]:
        keys: set[str] = set()
        for name, field in spec.input_model.model_fields.items():
            keys.add(name)
            if field.alias:
                keys.add(field.alias)
        return keys

    @staticmethod
    def _canonicalize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        prepared: dict[str, Any] = {}
        for key, value in (arguments or {}).items():
            canonical = {
                "tenantId": "tenant_id",
                "projectId": "project_id",
                "project": "project_id",
                "activityId": "activity_id",
                "task_id": "activity_id",
                "id": "activity_id",
                "idempotencyKey": "idempotency_key",
                "assignee_id": "assigneeId",
                "assignee_email": "assigneeEmail",
                "include_completed": "includeCompleted",
            }.get(key, key)
            if canonical not in prepared or prepared.get(canonical) in (None, "", {}, []):
                prepared[canonical] = value
        return prepared

    @staticmethod
    def _authorize(spec: ToolSpec, context: ToolExecutionContext) -> None:
        roles = set(context.user_roles or [])
        if "*" in roles or "admin" in roles:
            return
        if not spec.required_permissions.issubset(roles):
            raise AuthorizationError(
                f"Missing permissions for {spec.name}: {sorted(spec.required_permissions - roles)}"
            )

    async def _execute_read(
        self,
        spec: ToolSpec,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        self._check_circuit(spec.name)
        last_error: Exception | None = None
        attempts = spec.retry_policy.max_attempts
        overall_start = time.perf_counter()
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(
                    self.executor.execute(spec.mcp_tool_name, arguments),
                    timeout=spec.timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - overall_start) * 1000)
                limited = self._limit_payload(result)
                self._record_success(spec.name)
                retry_count = attempt
                self._record_mcp_observation(
                    spec,
                    context,
                    status="success",
                    latency_ms=latency_ms,
                    retry_count=retry_count,
                )
                self._audit(
                    spec,
                    context,
                    arguments,
                    "success",
                    latency_ms,
                    limited,
                    retry_count=retry_count,
                    transport=self._transport_name(),
                )
                return ToolExecutionResult(
                    tool_name=spec.name,
                    status="success",
                    result=limited,
                    latency_ms=latency_ms,
                )
            except asyncio.TimeoutError as exc:
                last_error = exc
                self._record_failure(spec.name)
                if attempt + 1 >= attempts:
                    latency_ms = int((time.perf_counter() - overall_start) * 1000)
                    retry_count = attempt
                    self._record_mcp_observation(
                        spec,
                        context,
                        status="timeout",
                        latency_ms=latency_ms,
                        retry_count=retry_count,
                        error_code="MCP_TIMEOUT",
                    )
                    self._audit(
                        spec,
                        context,
                        arguments,
                        "timeout",
                        latency_ms,
                        None,
                        "MCP_TIMEOUT",
                        retry_count=retry_count,
                        transport=self._transport_name(),
                    )
                    raise MCPTimeoutError() from exc
            except Exception as exc:
                last_error = exc
                self._record_failure(spec.name)
                if attempt + 1 >= attempts:
                    latency_ms = int((time.perf_counter() - overall_start) * 1000)
                    retry_count = attempt
                    error_code = getattr(exc, "code", "MCP_TRANSIENT_ERROR")
                    self._record_mcp_observation(
                        spec,
                        context,
                        status="error",
                        latency_ms=latency_ms,
                        retry_count=retry_count,
                        error_code=error_code,
                    )
                    self._audit(
                        spec,
                        context,
                        arguments,
                        "error",
                        latency_ms,
                        None,
                        error_code,
                        retry_count=retry_count,
                        transport=self._transport_name(),
                    )
                    raise MCPTransientError(str(exc)) from exc
            await asyncio.sleep(spec.retry_policy.backoff_seconds * (2**attempt))
        raise MCPTransientError(str(last_error) if last_error else "read failed")

    async def _execute_write(
        self,
        spec: ToolSpec,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        logical_arguments = self._arguments_without_idempotency(arguments)
        idempotency_key = context.idempotency_key or arguments.get("idempotency_key") or self.build_idempotency_key(
            tenant_id=context.tenant_id,
            request_id=context.request_id,
            tool_name=spec.name,
            arguments=logical_arguments,
        )
        context = replace(context, idempotency_key=idempotency_key)
        call_arguments = {**logical_arguments, "idempotency_key": idempotency_key}
        arguments_hash = self.arguments_hash(logical_arguments)
        existing = self.repository.get_idempotency_record(idempotency_key)
        if existing:
            if existing["arguments_hash"] != arguments_hash:
                raise IdempotencyConflictError()
            if existing["status"] == "SUCCEEDED":
                return ToolExecutionResult(
                    tool_name=spec.name,
                    status="success",
                    result=existing.get("result"),
                    latency_ms=0,
                    idempotency_key=idempotency_key,
                    from_idempotency=True,
                )

        if not existing:
            self.repository.create_idempotency_record(
                key=idempotency_key,
                tenant_id=context.tenant_id,
                request_id=context.request_id,
                tool_name=spec.name,
                arguments_hash=arguments_hash,
            )

        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.executor.execute(
                    spec.mcp_tool_name,
                    call_arguments,
                    idempotency_key=idempotency_key,
                ),
                timeout=spec.timeout_seconds,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            limited = self._limit_payload(result)
            self.repository.update_idempotency_record(
                idempotency_key,
                status="SUCCEEDED",
                result=limited,
                error=None,
            )
            self._record_mcp_observation(
                spec,
                context,
                status="success",
                latency_ms=latency_ms,
                retry_count=0,
            )
            self._audit(
                spec,
                context,
                call_arguments,
                "success",
                latency_ms,
                limited,
                retry_count=0,
                transport=self._transport_name(),
            )
            return ToolExecutionResult(
                tool_name=spec.name,
                status="success",
                result=limited,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
            )
        except asyncio.TimeoutError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.repository.update_idempotency_record(
                idempotency_key,
                status="UNKNOWN",
                result=None,
                error="timeout after write attempt",
            )
            self._record_mcp_observation(
                spec,
                context,
                status="timeout",
                latency_ms=latency_ms,
                retry_count=0,
                error_code="MCP_TIMEOUT",
            )
            self._audit(
                spec,
                context,
                call_arguments,
                "timeout",
                latency_ms,
                None,
                "MCP_TIMEOUT",
                retry_count=0,
                transport=self._transport_name(),
            )
            raise MCPTimeoutError() from exc
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.repository.update_idempotency_record(
                idempotency_key,
                status="FAILED",
                result=None,
                error=str(exc),
            )
            self._record_mcp_observation(
                spec,
                context,
                status="error",
                latency_ms=latency_ms,
                retry_count=0,
                error_code="MCP_PERMANENT_ERROR",
            )
            self._audit(
                spec,
                context,
                call_arguments,
                "error",
                latency_ms,
                None,
                "MCP_PERMANENT_ERROR",
                retry_count=0,
                transport=self._transport_name(),
            )
            raise MCPPermanentError(str(exc)) from exc

    @staticmethod
    def arguments_hash(arguments: dict[str, Any]) -> str:
        raw = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _arguments_without_idempotency(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in arguments.items()
            if key not in {"idempotency_key", "idempotencyKey"}
        }

    @classmethod
    def build_idempotency_key(
        cls,
        *,
        tenant_id: str,
        request_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        entity_id = (
            arguments.get("activity_id")
            or arguments.get("activityId")
            or arguments.get("id")
            or arguments.get("task_id")
            or arguments.get("task_query")
            or arguments.get("title")
            or "none"
        )
        payload_hash = cls.arguments_hash(cls._arguments_without_idempotency(arguments))
        raw = f"{tenant_id}:{request_id}:{tool_name}:{entity_id}:{payload_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _audit(
        self,
        spec: ToolSpec,
        context: ToolExecutionContext,
        arguments: dict[str, Any],
        status: str,
        latency_ms: int,
        result: Any | None,
        error_code: str | None = None,
        *,
        retry_count: int = 0,
        transport: str | None = None,
    ) -> None:
        try:
            self.repository.append_tool_execution_audit(
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                thread_id=context.thread_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                intent=context.intent,
                tool_name=spec.name,
                tool_type=spec.type,
                status=status,
                latency_ms=latency_ms,
                arguments=arguments,
                result=result,
                error_code=error_code,
                retry_count=retry_count,
                transport=transport or self._transport_name(),
            )
        except Exception:
            logger.exception("Failed to append tool execution audit")

    def _record_mcp_observation(
        self,
        spec: ToolSpec,
        context: ToolExecutionContext,
        *,
        status: str,
        latency_ms: int,
        retry_count: int,
        error_code: str | None = None,
    ) -> None:
        transport = self._transport_name()
        success = status == "success"
        record_mcp_call(
            tool_name=spec.name,
            duration_ms=latency_ms,
            success=success,
            retry_count=retry_count,
            transport=transport,
            tenant_id=context.tenant_id,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            error_code=error_code,
        )
        if self.metrics:
            self.metrics.increment("mcp_calls_total", api_version=context.api_version)
            self.metrics.increment("agent_mcp_calls_total", api_version=context.api_version)
        logger.info(
            "mcp_tool_call",
            extra={
                "request_id": context.request_id,
                "correlation_id": context.correlation_id,
                "api_version": context.api_version,
                "thread_id": context.thread_id,
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "activity_id": context.activity_id,
                "user_id": context.user_id,
                "intent": context.intent,
                "tool_name": spec.name,
                "latency_ms": latency_ms,
                "duration_ms": latency_ms,
                "status": status,
                "success": success,
                "retry_count": retry_count,
                "transport": transport,
                "error_code": error_code,
                "idempotency_key_hash": _hash_for_logs(context.idempotency_key),
            },
        )

    def _transport_name(self) -> str:
        board_tools = getattr(self.executor, "board_tools", None)
        client = getattr(board_tools, "client", None)
        settings = getattr(client, "settings", None)
        return str(getattr(settings, "mcp_board_transport", "unknown") or "unknown")

    def _limit_payload(self, payload: Any) -> Any:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) <= self.result_max_chars:
            return payload
        return {
            "truncated": True,
            "max_chars": self.result_max_chars,
            "preview": text[: self.result_max_chars],
        }

    def _check_circuit(self, tool_name: str) -> None:
        count, updated_at = self._failure_counts.get(tool_name, (0, 0.0))
        if count >= 5 and time.monotonic() - updated_at < 30:
            raise MCPTransientError(f"Circuit breaker open for {tool_name}")

    def _record_failure(self, tool_name: str) -> None:
        count, _ = self._failure_counts.get(tool_name, (0, 0.0))
        self._failure_counts[tool_name] = (count + 1, time.monotonic())

    def _record_success(self, tool_name: str) -> None:
        self._failure_counts.pop(tool_name, None)


def _hash_for_logs(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

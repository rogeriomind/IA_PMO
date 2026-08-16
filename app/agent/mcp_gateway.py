from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
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
    ToolNotAllowedError,
    ToolValidationError,
)
from app.agent.latency import record_mcp_call
from app.agent.tool_registry import ToolRegistry, ToolSpec
from app.infrastructure.observability.metrics import AgentMetrics
from app.mcp.board_tools import BoardTools
from app.storage.repository import PendingActionRepository

logger = logging.getLogger(__name__)


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

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        if tool_name == "board_search_tasks":
            return await self.board_tools.search_tasks(
                query=arguments.get("search") or arguments.get("query") or "",
                project_id=arguments.get("project_id"),
            )
        if tool_name == "board_get_task":
            task_id = arguments.get("id") or arguments.get("task_id")
            return await self.board_tools.get_task(task_id=task_id)
        if tool_name == "board_search_users":
            return await self.board_tools.search_users(
                query=arguments.get("query"),
                limit=arguments.get("limit") or 20,
            )
        if tool_name == "board_create_task":
            return await self.board_tools.create_task(arguments, idempotency_key=idempotency_key)
        if tool_name == "board_update_task":
            return await self.board_tools.update_task(
                task_id=arguments.get("task_id") or arguments.get("id"),
                task_query=arguments.get("task_query"),
                fields=arguments.get("fields") or {},
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_move_task":
            return await self.board_tools.move_task(
                task_id=arguments.get("task_id") or arguments.get("id"),
                task_query=arguments.get("task_query"),
                status=arguments.get("status"),
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_add_comment":
            return await self.board_tools.add_comment(
                task_id=arguments.get("task_id") or arguments.get("id"),
                task_query=arguments.get("task_query"),
                comment=arguments.get("comment"),
                idempotency_key=idempotency_key,
            )
        if tool_name == "board_get_project_status":
            return await self.board_tools.get_project_status(
                project_id=arguments.get("project_id"),
                query=arguments.get("query"),
            )
        if tool_name == "board_list_blockers":
            return await self.board_tools.list_blockers(project_id=arguments.get("project_id"))
        if tool_name == "board_list_my_tasks":
            try:
                return await self.board_tools.list_my_tasks(
                    user_id=arguments.get("user_id"),
                    project_id=arguments.get("project_id"),
                    assignee_id=arguments.get("assigneeId"),
                    assignee_email=arguments.get("assigneeEmail"),
                )
            except TypeError:
                return await self.board_tools.list_my_tasks(
                    user_id=arguments.get("user_id") or arguments.get("assigneeId") or "",
                    project_id=arguments.get("project_id"),
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
        validated = self._validate_arguments(spec, arguments)
        self._authorize(spec, context)

        if spec.requires_confirmation and context.approval_status != "approved":
            raise ConfirmationRequiredError()

        if spec.type == "write":
            return await self._execute_write(spec, validated, context)
        return await self._execute_read(spec, validated, context)

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
        idempotency_key = context.idempotency_key or self.build_idempotency_key(
            tenant_id=context.tenant_id,
            request_id=context.request_id,
            tool_name=spec.name,
            arguments=arguments,
        )
        arguments_hash = self.arguments_hash(arguments)
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
                    arguments,
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
                arguments,
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
                arguments,
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
                arguments,
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
            arguments.get("id")
            or arguments.get("task_id")
            or arguments.get("task_query")
            or arguments.get("title")
            or "none"
        )
        payload_hash = cls.arguments_hash(arguments)
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

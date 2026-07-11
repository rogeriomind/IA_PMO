from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.agent.context import ToolExecutionContext
from app.agent.errors import AgentError, MCPTimeoutError
from app.agent.mcp_gateway import MCPGateway
from app.storage.repository import PendingActionRepository, utcnow


APPROVAL_WORDS = {
    "sim",
    "confirmo",
    "confirmar",
    "pode executar",
    "aprovar",
}

REJECTION_WORDS = {
    "nao",
    "não",
    "cancelar",
    "rejeitar",
    "nao confirmar",
    "não confirmar",
}


class AgentConfirmationService:
    def __init__(self, repository: PendingActionRepository, gateway: MCPGateway):
        self.repository = repository
        self.gateway = gateway

    async def reject(
        self,
        *,
        pending_action_id: str,
        tenant_id: str,
        thread_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        pending = self.repository.get_pending_action(pending_action_id)
        validation = self._validate_pending_context(
            pending,
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            allow_pending_only=True,
        )
        if validation:
            return validation
        self.repository.transition_pending_action(
            pending_action_id,
            from_status="pending",
            to_status="rejected",
        )
        return {
            "status": "cancelled",
            "message": "Ok, nenhuma alteracao foi realizada no board.",
            "data": {},
        }

    async def approve_and_execute(
        self,
        *,
        pending_action_id: str,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        user_roles: list[str],
    ) -> dict[str, Any]:
        pending = self.repository.get_pending_action(pending_action_id)
        validation = self._validate_pending_context(
            pending,
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            allow_pending_only=True,
        )
        if validation:
            return validation

        assert pending is not None
        transitioned = self.repository.transition_pending_action(
            pending_action_id,
            from_status="pending",
            to_status="executing",
        )
        if not transitioned:
            return {
                "status": "conflict",
                "message": "Essa confirmacao ja foi utilizada.",
                "data": {},
                "error_code": "CONFIRMATION_ALREADY_USED",
            }

        operations = list(pending.get("operations") or [])
        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for operation in operations:
            tool_name = operation["tool_name"]
            arguments = operation.get("arguments") or {}
            intent = operation.get("intent") or _intent_for_tool(tool_name)
            idempotency_key = _operation_idempotency_key(
                tenant_id=tenant_id,
                request_id=pending.get("request_id") or pending_action_id,
                pending_action_id=pending_action_id,
                tool_name=tool_name,
                arguments=arguments,
            )
            try:
                execution = await self.gateway.execute(
                    tool_name=tool_name,
                    arguments=arguments,
                    context=ToolExecutionContext(
                        request_id=pending.get("request_id") or pending_action_id,
                        correlation_id=pending.get("correlation_id") or pending_action_id,
                        thread_id=thread_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        user_roles=user_roles,
                        intent=intent,
                        approval_status="approved",
                        idempotency_key=idempotency_key,
                    ),
                )
                results.append(
                    {
                        "tool_name": tool_name,
                        "status": execution.status,
                        "result": execution.result,
                        "idempotency_key": execution.idempotency_key,
                        "from_idempotency": execution.from_idempotency,
                    }
                )
            except MCPTimeoutError as exc:
                failures.append({"tool_name": tool_name, "status": "unknown", "error": exc.user_message})
                break
            except AgentError as exc:
                failures.append({"tool_name": tool_name, "status": "failed", "error": exc.user_message})
            except Exception as exc:
                failures.append({"tool_name": tool_name, "status": "failed", "error": str(exc)})

        read_after_write = await self._read_after_write(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            user_roles=user_roles,
            pending=pending,
            results=results,
        )
        status = _final_status(results, failures, len(operations))
        result_payload = {
            "operations": results,
            "failures": failures,
            "read_after_write": read_after_write,
        }
        self.repository.mark_v2_pending_action_result(
            pending_action_id,
            status=status,
            result=result_payload,
            error="; ".join(item["error"] for item in failures) if failures else None,
        )
        return {
            "status": "completed" if status == "completed" else "degraded" if status == "partial" else "error",
            "message": _execution_message(pending.get("action_type") or "", status, failures),
            "data": result_payload,
            "confirmation_status": status,
        }

    def _validate_pending_context(
        self,
        pending: dict[str, Any] | None,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        allow_pending_only: bool,
    ) -> dict[str, Any] | None:
        if not pending:
            return {
                "status": "not_found",
                "message": "Nao encontrei essa confirmacao pendente.",
                "data": {},
                "error_code": "CONFIRMATION_NOT_FOUND",
            }
        if pending.get("tenant_id") != tenant_id:
            return _unauthorized("CONFIRMATION_TENANT_MISMATCH")
        if (pending.get("thread_id") or pending.get("conversation_id")) != thread_id:
            return _unauthorized("CONFIRMATION_THREAD_MISMATCH")
        if pending.get("user_id") != user_id:
            return _unauthorized("CONFIRMATION_USER_MISMATCH")
        if allow_pending_only and pending.get("status") != "pending":
            return {
                "status": "conflict",
                "message": "Essa confirmacao nao esta mais pendente.",
                "data": {},
                "error_code": "CONFIRMATION_NOT_PENDING",
            }
        if _is_expired(pending.get("expires_at")):
            self.repository.mark_v2_pending_action_result(pending["id"], status="expired", error="expired")
            return {
                "status": "validation_error",
                "message": "Essa confirmacao expirou. Gere uma nova confirmacao para continuar.",
                "data": {},
                "error_code": "CONFIRMATION_EXPIRED",
            }
        return None

    async def _read_after_write(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        user_roles: list[str],
        pending: dict[str, Any],
        results: list[dict[str, Any]],
    ) -> Any | None:
        task_id = None
        for operation in pending.get("operations") or []:
            args = operation.get("arguments") or {}
            task_id = args.get("task_id") or args.get("id")
            if task_id:
                break
        if not task_id:
            for result in results:
                payload = result.get("result")
                if isinstance(payload, dict):
                    task_id = payload.get("id") or payload.get("task_id")
                    if task_id:
                        break
        if not task_id:
            return None
        try:
            execution = await self.gateway.execute(
                tool_name="board_get_task",
                arguments={"id": task_id},
                context=ToolExecutionContext(
                    request_id=pending.get("request_id") or pending["id"],
                    correlation_id=pending.get("correlation_id") or pending["id"],
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_roles=user_roles,
                    intent="task.get",
                    approval_status="not_required",
                ),
            )
            return execution.result
        except Exception as exc:
            return {"partial": True, "error": str(exc)}


def is_approval_text(value: str | None) -> bool:
    return _plain(value or "") in {_plain(item) for item in APPROVAL_WORDS}


def is_rejection_text(value: str | None) -> bool:
    return _plain(value or "") in {_plain(item) for item in REJECTION_WORDS}


def _plain(value: str) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def _is_expired(raw_expires_at: str | None) -> bool:
    if not raw_expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(raw_expires_at)
    except ValueError:
        return False
    now = utcnow()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=now.tzinfo)
    return expires_at < now


def _operation_idempotency_key(
    *,
    tenant_id: str,
    request_id: str,
    pending_action_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    entity = arguments.get("task_id") or arguments.get("id") or arguments.get("title") or "none"
    payload_hash = hashlib.sha256(
        json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    raw = f"{tenant_id}:{request_id}:{pending_action_id}:{tool_name}:{entity}:{payload_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _intent_for_tool(tool_name: str) -> str:
    return {
        "board_create_task": "task.create",
        "board_update_task": "task.update",
        "board_add_comment": "task.comment",
        "board_move_task": "task.move",
    }.get(tool_name, "unknown")


def _final_status(
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    expected_count: int,
) -> str:
    if any(item["status"] == "unknown" for item in failures):
        return "unknown"
    if failures and results:
        return "partial"
    if failures:
        return "failed"
    if len(results) == expected_count:
        return "completed"
    return "failed"


def _execution_message(action_type: str, status: str, failures: list[dict[str, Any]]) -> str:
    if status == "completed":
        return {
            "task.create": "Atividade criada com sucesso no board.",
            "task.update": "Atividade atualizada com sucesso no board.",
        }.get(action_type, "Acao executada com sucesso no board.")
    if status == "partial":
        failed_tools = ", ".join(item["tool_name"] for item in failures)
        return f"A atualizacao foi parcialmente executada, mas houve falha em: {failed_tools}."
    if status == "unknown":
        return "A escrita no board atingiu timeout e ficou com estado desconhecido. Nao vou repetir automaticamente."
    return "Nao consegui executar a acao no board."


def _unauthorized(code: str) -> dict[str, Any]:
    return {
        "status": "unauthorized",
        "message": "Essa confirmacao nao pertence ao mesmo usuario, conversa ou tenant.",
        "data": {},
        "error_code": code,
    }

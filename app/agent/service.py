from __future__ import annotations

from typing import Any

from app.agent.context import ToolExecutionContext
from app.agent.errors import AgentError
from app.agent.intents import INTENT_TO_TOOL
from app.agent.mcp_gateway import MCPGateway
from app.agent.observability import ObservabilityService
from app.agent.routing import is_explicit_confirmation, is_explicit_rejection
from app.agent.state import AgentState
from app.agent.thread_lock import ThreadLockManager
from app.storage.repository import PendingActionRepository


class AgentWorkflowService:
    def __init__(
        self,
        *,
        graph,
        gateway: MCPGateway,
        repository: PendingActionRepository,
        observability: ObservabilityService,
        thread_locks: ThreadLockManager,
    ) -> None:
        self.graph = graph
        self.gateway = gateway
        self.repository = repository
        self.observability = observability
        self.thread_locks = thread_locks

    async def handle_message(self, state: AgentState) -> dict[str, Any]:
        trace = await self.observability.trace_request(
            name="v1.agent.message",
            request_id=state["request_id"],
            correlation_id=state["correlation_id"],
            thread_id=state["thread_id"],
            tenant_id=state["tenant_id"],
            user_id=state["user_id"],
            input_payload={
                "thread_id": state["thread_id"],
                "channel": state.get("channel"),
                "message": state.get("original_message"),
            },
        )
        async with self.thread_locks.acquire(tenant_id=state["tenant_id"], thread_id=state["thread_id"]):
            try:
                result = await self.graph.ainvoke(state)
            except Exception as exc:
                result = self._error_result(state, exc)
            await self.observability.update_trace(trace, output=result)
            return self._response_from_state(result)

    async def handle_confirmation(
        self,
        *,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        user_roles: list[str],
        confirmation_id: str,
        approved: bool,
        message: str | None,
    ) -> dict[str, Any]:
        trace = await self.observability.trace_request(
            name="v1.agent.confirmation",
            request_id=request_id,
            correlation_id=correlation_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={
                "thread_id": thread_id,
                "confirmation_id": confirmation_id,
                "approved": approved,
            },
        )
        async with self.thread_locks.acquire(tenant_id=tenant_id, thread_id=thread_id):
            result = await self._handle_confirmation_inner(
                request_id=request_id,
                correlation_id=correlation_id,
                thread_id=thread_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_roles=user_roles,
                confirmation_id=confirmation_id,
                approved=approved,
                message=message,
            )
            await self.observability.update_trace(trace, output=result)
            return result

    async def _handle_confirmation_inner(
        self,
        *,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        user_roles: list[str],
        confirmation_id: str,
        approved: bool,
        message: str | None,
    ) -> dict[str, Any]:
        pending = self.repository.get_pending_action(confirmation_id)
        if not pending or pending["conversation_id"] != thread_id:
            return self._error_response(
                request_id=request_id,
                thread_id=thread_id,
                code="CONFIRMATION_NOT_FOUND",
                message="Nao encontrei essa confirmacao pendente.",
            )
        if pending["status"] != "PENDING":
            return self._error_response(
                request_id=request_id,
                thread_id=thread_id,
                code="CONFIRMATION_NOT_PENDING",
                message="Essa confirmacao nao esta mais pendente.",
            )

        if not approved or is_explicit_rejection(message):
            self.repository.mark_cancelled(confirmation_id)
            return {
                "request_id": request_id,
                "thread_id": thread_id,
                "status": "rejected",
                "intent": (pending.get("action_payload") or {}).get("intent"),
                "message": "Ok, nenhuma alteracao foi realizada no board.",
                "data": {},
            }

        if approved and not is_explicit_confirmation(message):
            return self._error_response(
                request_id=request_id,
                thread_id=thread_id,
                code="CONFIRMATION_NOT_EXPLICIT",
                message="Preciso de uma confirmacao explicita para executar essa alteracao.",
            )

        payload = pending.get("action_payload") or {}
        tool_name = pending["action_type"]
        tool_input = payload.get("tool_input") or {}
        intent = payload.get("intent") or _intent_for_tool(tool_name)
        original_request_id = payload.get("request_id") or request_id
        idempotency_key = self.gateway.build_idempotency_key(
            tenant_id=tenant_id,
            request_id=original_request_id,
            tool_name=tool_name,
            arguments=tool_input,
        )
        self.repository.mark_confirmed(confirmation_id)
        try:
            execution = await self.gateway.execute(
                tool_name=tool_name,
                arguments=tool_input,
                context=ToolExecutionContext(
                    request_id=original_request_id,
                    correlation_id=correlation_id,
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_roles=user_roles,
                    intent=intent,
                    approval_status="approved",
                    idempotency_key=idempotency_key,
                ),
            )
            read_after_write = await self._read_after_write(
                request_id=original_request_id,
                correlation_id=correlation_id,
                thread_id=thread_id,
                tenant_id=tenant_id,
                user_id=user_id,
                user_roles=user_roles,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=execution.result,
            )
            result_payload = {
                "result": execution.result,
                "read_after_write": read_after_write,
                "idempotency_key": execution.idempotency_key,
                "from_idempotency": execution.from_idempotency,
            }
            self.repository.mark_executed(confirmation_id, result_payload)
            return {
                "request_id": request_id,
                "thread_id": thread_id,
                "status": "completed",
                "intent": intent,
                "message": _success_message(tool_name, read_after_write),
                "data": result_payload,
            }
        except Exception as exc:
            self.repository.mark_failed(confirmation_id, str(exc))
            code = getattr(exc, "code", "AGENT_ERROR")
            message_text = exc.user_message if isinstance(exc, AgentError) else "Nao consegui executar a acao no board."
            return self._error_response(
                request_id=request_id,
                thread_id=thread_id,
                code=code,
                message=message_text,
            )

    async def _read_after_write(
        self,
        *,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        user_roles: list[str],
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: Any,
    ) -> Any | None:
        task_id = tool_input.get("task_id") or tool_input.get("id")
        if not task_id and isinstance(tool_result, dict):
            task_id = tool_result.get("id") or tool_result.get("task_id")
        if not task_id:
            return None
        try:
            read = await self.gateway.execute(
                tool_name="board_get_task",
                arguments={"id": task_id},
                context=ToolExecutionContext(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_roles=user_roles,
                    intent="task.get",
                    approval_status="not_required",
                ),
            )
            return read.result
        except Exception as exc:
            return {"partial": True, "error": str(exc)}

    def _response_from_state(self, state: AgentState) -> dict[str, Any]:
        status = state.get("status") or "completed"
        response: dict[str, Any] = {
            "request_id": state["request_id"],
            "thread_id": state["thread_id"],
            "status": status,
            "intent": state.get("intent"),
            "message": state.get("final_answer") or "Solicitacao processada.",
            "data": state.get("data") or {},
        }
        if status == "awaiting_confirmation":
            response["confirmation"] = {
                "confirmation_id": state.get("confirmation_id"),
                "action": state.get("selected_tool"),
                "preview": state.get("action_preview") or {},
            }
        if status == "error":
            error = (state.get("errors") or [{}])[0]
            response["error"] = {
                "code": error.get("code", "AGENT_ERROR"),
                "message": response["message"],
            }
        return response

    def _error_result(self, state: AgentState, exc: Exception) -> AgentState:
        code = getattr(exc, "code", "AGENT_ERROR")
        message = exc.user_message if isinstance(exc, AgentError) else "Nao consegui processar sua mensagem agora."
        return {
            **state,
            "status": "error",
            "final_answer": message,
            "errors": [{"code": code, "message": str(exc)}],
        }

    @staticmethod
    def _error_response(*, request_id: str, thread_id: str, code: str, message: str) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "thread_id": thread_id,
            "status": "error",
            "intent": None,
            "message": message,
            "data": {},
            "error": {"code": code, "message": message},
        }


def _intent_for_tool(tool_name: str) -> str:
    for intent, mapped_tool in INTENT_TO_TOOL.items():
        if mapped_tool == tool_name:
            return intent
    return "unknown"


def _success_message(tool_name: str, read_after_write: Any | None) -> str:
    base = {
        "board_create_task": "Tarefa criada com sucesso no board.",
        "board_update_task": "Tarefa atualizada com sucesso no board.",
        "board_move_task": "Tarefa movida com sucesso no board.",
        "board_add_comment": "Comentario adicionado com sucesso no board.",
    }.get(tool_name, "Acao executada com sucesso no board.")
    if isinstance(read_after_write, dict) and read_after_write.get("partial"):
        return base + " Nao consegui confirmar a leitura final automaticamente."
    return base


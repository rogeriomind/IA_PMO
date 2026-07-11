from __future__ import annotations

import time
from typing import Any

from app.agent.errors import ThreadLockedError
from app.agent.main_graph.state import PMOAgentState
from app.agent.thread_lock import ThreadLockManager
from app.api.dependencies import RequestContext
from app.api.schemas.agent_v2 import AgentEventEnvelope, AgentThreadSnapshot, AgentV2Response
from app.config import Settings
from app.observability.langfuse import LangfuseTracer, sanitize_payload
from app.storage.repository import PendingActionRepository


class AgentV2Service:
    def __init__(
        self,
        *,
        graph,
        repository: PendingActionRepository,
        settings: Settings,
        thread_locks: ThreadLockManager,
        tracer: LangfuseTracer,
    ):
        self.graph = graph
        self.repository = repository
        self.settings = settings
        self.thread_locks = thread_locks
        self.tracer = tracer

    async def handle_event(
        self,
        payload: AgentEventEnvelope,
        context: RequestContext,
    ) -> AgentV2Response:
        replay = self.repository.get_agent_event_by_event_id(payload.event_id)
        if replay:
            response_payload = dict(replay.get("output_payload_sanitized") or {})
            data = dict(response_payload.get("data") or {})
            data["replay"] = True
            response_payload["data"] = data
            return AgentV2Response.model_validate(response_payload)

        start = time.perf_counter()
        trace = self.tracer.start_trace(
            name="v2.agent.event",
            session_id=payload.thread_id,
            user_id=payload.user.id,
            metadata={
                "request_id": payload.request_id,
                "correlation_id": payload.correlation_id,
                "event_id": payload.event_id,
                "thread_id": payload.thread_id,
                "tenant_id": payload.tenant_id,
                "channel": payload.channel,
                "message_type": payload.message_type,
            },
            input_payload=payload.model_dump(mode="json"),
        )
        try:
            async with self.thread_locks.acquire(tenant_id=payload.tenant_id, thread_id=payload.thread_id):
                state = _state_from_payload(payload, context)
                result: PMOAgentState = await self.graph.ainvoke(state)
        except ThreadLockedError:
            result = _conflict_state(payload)
        except Exception as exc:
            result = _error_state(payload, exc)

        response_payload = result.get("api_response") or _fallback_response(payload)
        self.tracer.update_trace(trace, output=response_payload)
        latency_ms = int((time.perf_counter() - start) * 1000)
        self.repository.append_agent_event(
            event_id=payload.event_id,
            request_id=payload.request_id,
            correlation_id=payload.correlation_id,
            thread_id=payload.thread_id,
            tenant_id=payload.tenant_id,
            user_id=payload.user.id,
            message_type=payload.message_type,
            flow=response_payload.get("flow"),
            step=response_payload.get("step"),
            input_payload_sanitized=sanitize_payload(payload.model_dump(mode="json")),
            output_payload_sanitized=sanitize_payload(response_payload),
            status=response_payload.get("status") or "error",
            latency_ms=latency_ms,
        )
        return AgentV2Response.model_validate(response_payload)

    async def get_thread(self, *, tenant_id: str, thread_id: str) -> AgentThreadSnapshot | None:
        thread = self.repository.get_agent_thread(tenant_id=tenant_id, thread_id=thread_id)
        if not thread:
            return None
        safe = {
            "thread_id": thread["thread_id"],
            "tenant_id": thread["tenant_id"],
            "channel": thread["channel"],
            "user_id": thread["user_id"],
            "user_name": thread.get("user_name"),
            "current_flow": thread["current_flow"],
            "current_step": thread["current_step"],
            "state_summary": _safe_thread_summary(thread.get("state_summary") or {}),
            "last_event_id": thread.get("last_event_id"),
            "created_at": thread.get("created_at"),
            "updated_at": thread.get("updated_at"),
            "expires_at": thread.get("expires_at"),
        }
        return AgentThreadSnapshot.model_validate(safe)


def _state_from_payload(payload: AgentEventEnvelope, context: RequestContext) -> PMOAgentState:
    return {
        "request_id": payload.request_id or context.request_id,
        "correlation_id": payload.correlation_id or context.correlation_id,
        "event_id": payload.event_id,
        "thread_id": payload.thread_id,
        "tenant_id": payload.tenant_id,
        "channel": payload.channel,
        "user_id": payload.user.id,
        "user_name": payload.user.name or "",
        "username": payload.user.username,
        "user_roles": context.user_roles,
        "message_type": payload.message_type,
        "message_text": payload.content.text,
        "callback_data": payload.content.callback_data,
        "metadata": payload.metadata.model_dump(mode="json"),
        "current_flow": "main_menu",
        "current_step": "new_event",
        "response_data": {},
    }


def _conflict_state(payload: AgentEventEnvelope) -> PMOAgentState:
    response = {
        "request_id": payload.request_id,
        "correlation_id": payload.correlation_id,
        "thread_id": payload.thread_id,
        "status": "conflict",
        "flow": "unknown",
        "step": "thread_locked",
        "message": "Esta conversa ja esta sendo processada. Tente novamente em instantes.",
        "ui": {"type": "none", "options": []},
        "data": {},
        "requires_confirmation": False,
        "confirmation": None,
        "error": {"code": "THREAD_LOCKED", "message": "Thread is locked"},
    }
    return {"api_response": response}


def _error_state(payload: AgentEventEnvelope, exc: Exception) -> PMOAgentState:
    message = getattr(exc, "user_message", "Nao consegui processar sua mensagem agora.")
    code = getattr(exc, "code", "AGENT_ERROR")
    response = {
        "request_id": payload.request_id,
        "correlation_id": payload.correlation_id,
        "thread_id": payload.thread_id,
        "status": "error",
        "flow": "unknown",
        "step": "unhandled_error",
        "message": message,
        "ui": {"type": "none", "options": []},
        "data": {},
        "requires_confirmation": False,
        "confirmation": None,
        "error": {"code": code, "message": message},
    }
    return {"api_response": response}


def _fallback_response(payload: AgentEventEnvelope) -> dict[str, Any]:
    return {
        "request_id": payload.request_id,
        "correlation_id": payload.correlation_id,
        "thread_id": payload.thread_id,
        "status": "error",
        "flow": "unknown",
        "step": "missing_response",
        "message": "Nao consegui montar a resposta do agente.",
        "ui": {"type": "none", "options": []},
        "data": {},
        "requires_confirmation": False,
        "confirmation": None,
        "error": {"code": "MISSING_AGENT_RESPONSE", "message": "Missing graph response"},
    }


def _safe_thread_summary(summary: dict[str, Any]) -> dict[str, Any]:
    hidden = {"pending_payload", "operations_payload"}
    return {key: value for key, value in sanitize_payload(summary).items() if key not in hidden}

from __future__ import annotations

from typing import Any

from app.observability.langfuse import LangfuseTracer, TraceContext


class ObservabilityService:
    def __init__(self, tracer: LangfuseTracer):
        self.tracer = tracer

    async def trace_request(
        self,
        *,
        name: str,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        input_payload: dict[str, Any],
    ) -> TraceContext:
        return self.tracer.start_trace(
            name=name,
            session_id=thread_id,
            user_id=user_id,
            metadata={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
            },
            input_payload=input_payload,
        )

    async def trace_model_call(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def trace_tool_call(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def record_error(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def update_trace(self, trace: TraceContext | None, **kwargs: Any) -> None:
        self.tracer.update_trace(trace, **kwargs)


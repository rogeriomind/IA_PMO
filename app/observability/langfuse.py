from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from uuid import uuid4

from app.config import Settings

logger = logging.getLogger(__name__)

SENSITIVE_KEY_PARTS = (
    "authorization",
    "token",
    "secret",
    "password",
    "cookie",
    "api_key",
    "apikey",
    "access_key",
)


def sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        clean = {}
        for key, value in payload.items():
            if any(part in key.casefold() for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = sanitize_payload(value)
        return clean
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload


@dataclass
class TraceContext:
    trace_id: str
    trace: Any | None = None


class LangfuseTracer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = settings.langfuse_configured
        self.client = None
        if self.enabled:
            try:
                from langfuse import Langfuse

                self.client = Langfuse(
                    public_key=settings.langfuse_public_key.get_secret_value(),
                    secret_key=settings.langfuse_secret_key.get_secret_value(),
                    host=settings.langfuse_host,
                )
            except Exception:
                logger.exception("Langfuse initialization failed; traces disabled")
                self.enabled = False

    def start_trace(
        self,
        *,
        name: str,
        session_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> TraceContext:
        trace_id = str(uuid4())
        if not self.enabled or not self.client:
            return TraceContext(trace_id=trace_id)
        try:
            trace = self.client.trace(
                id=trace_id,
                name=name,
                session_id=session_id,
                user_id=user_id,
                metadata=sanitize_payload(metadata or {}),
                input=sanitize_payload(input_payload or {}),
            )
            return TraceContext(trace_id=trace_id, trace=trace)
        except Exception:
            logger.exception("Failed to create Langfuse trace")
            return TraceContext(trace_id=trace_id)

    @contextmanager
    def span(
        self,
        trace_context: TraceContext | None,
        name: str,
        *,
        input_payload: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        span = None
        if self.enabled and trace_context and trace_context.trace:
            try:
                span = trace_context.trace.span(
                    name=name,
                    input=sanitize_payload(input_payload),
                    metadata=sanitize_payload(metadata or {}),
                )
            except Exception:
                logger.exception("Failed to create Langfuse span")
                span = None
        try:
            yield
        except Exception as exc:
            if span:
                try:
                    span.end(output={"error": str(exc)}, level="ERROR")
                except Exception:
                    logger.exception("Failed to close Langfuse span with error")
            raise
        else:
            if span:
                try:
                    span.end()
                except Exception:
                    logger.exception("Failed to close Langfuse span")

    def update_trace(self, trace_context: TraceContext | None, **kwargs: Any) -> None:
        if not self.enabled or not trace_context or not trace_context.trace:
            return
        try:
            clean = {key: sanitize_payload(value) for key, value in kwargs.items()}
            trace_context.trace.update(**clean)
        except Exception:
            logger.exception("Failed to update Langfuse trace")

    def flush(self) -> None:
        if self.enabled and self.client:
            try:
                self.client.flush()
            except Exception:
                logger.exception("Failed to flush Langfuse")


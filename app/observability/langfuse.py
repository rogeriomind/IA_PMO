from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from uuid import uuid4

from pydantic import BaseModel

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
    if isinstance(payload, BaseModel):
        return sanitize_payload(payload.model_dump(mode="json"))
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
    if isinstance(payload, tuple):
        return [sanitize_payload(item) for item in payload]
    return payload


@dataclass
class TraceContext:
    trace_id: str
    trace: Any | None = None
    ended: bool = False


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
        fallback_trace_id = str(uuid4())
        if not self.enabled or not self.client:
            return TraceContext(trace_id=fallback_trace_id)
        try:
            trace_metadata = sanitize_payload(metadata or {})
            trace_input = sanitize_payload(input_payload or {})
            if hasattr(self.client, "start_observation"):
                trace = self.client.start_observation(
                    as_type="span",
                    name=name,
                    input=trace_input,
                    metadata=trace_metadata,
                )
                if hasattr(trace, "update_trace"):
                    trace.update_trace(
                        name=name,
                        session_id=session_id,
                        user_id=user_id,
                        metadata=trace_metadata,
                        input=trace_input,
                    )
                return TraceContext(trace_id=getattr(trace, "trace_id", fallback_trace_id), trace=trace)
            trace = self.client.trace(
                id=fallback_trace_id,
                name=name,
                session_id=session_id,
                user_id=user_id,
                metadata=trace_metadata,
                input=trace_input,
            )
            return TraceContext(trace_id=fallback_trace_id, trace=trace)
        except Exception:
            logger.exception("Failed to create Langfuse trace")
            return TraceContext(trace_id=fallback_trace_id)

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
                span = self._start_child_observation(
                    trace_context,
                    as_type="span",
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
                    self._update_observation(
                        span,
                        output={"error": str(exc)},
                        level="ERROR",
                        status_message=str(exc),
                    )
                    span.end()
                except Exception:
                    logger.exception("Failed to close Langfuse span with error")
            raise
        else:
            if span:
                try:
                    span.end()
                except Exception:
                    logger.exception("Failed to close Langfuse span")

    @contextmanager
    def generation(
        self,
        trace_context: TraceContext | None,
        name: str,
        *,
        input_payload: Any | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
    ) -> Iterator[Any | None]:
        generation = None
        if self.enabled and trace_context and trace_context.trace:
            try:
                generation = self._start_child_observation(
                    trace_context,
                    as_type="generation",
                    name=name,
                    input=sanitize_payload(input_payload),
                    metadata=sanitize_payload(metadata or {}),
                    model=model,
                    model_parameters=model_parameters,
                )
            except Exception:
                logger.exception("Failed to create Langfuse generation")
                generation = None
        try:
            yield generation
        except Exception as exc:
            if generation:
                try:
                    self._update_observation(
                        generation,
                        output={"error": str(exc)},
                        level="ERROR",
                        status_message=str(exc),
                    )
                    generation.end()
                except Exception:
                    logger.exception("Failed to close Langfuse generation with error")
            raise
        else:
            if generation:
                try:
                    generation.end()
                except Exception:
                    logger.exception("Failed to close Langfuse generation")

    def update_observation(self, observation: Any | None, **kwargs: Any) -> None:
        if not observation:
            return
        try:
            self._update_observation(observation, **kwargs)
        except Exception:
            logger.exception("Failed to update Langfuse observation")

    def update_trace(self, trace_context: TraceContext | None, **kwargs: Any) -> None:
        if not self.enabled or not trace_context or not trace_context.trace:
            return
        try:
            clean = {key: sanitize_payload(value) for key, value in kwargs.items()}
            trace = trace_context.trace
            if hasattr(trace, "update_trace"):
                trace_kwargs = {key: clean[key] for key in ("name", "user_id", "session_id", "metadata", "tags", "public") if key in clean}
                if "input" in clean:
                    trace_kwargs["input"] = clean["input"]
                if "input_payload" in clean:
                    trace_kwargs["input"] = clean["input_payload"]
                if "output" in clean:
                    trace_kwargs["output"] = clean["output"]
                if trace_kwargs:
                    trace.update_trace(**trace_kwargs)
                observation_kwargs = {}
                if "input" in clean:
                    observation_kwargs["input"] = clean["input"]
                if "input_payload" in clean:
                    observation_kwargs["input"] = clean["input_payload"]
                if "output" in clean:
                    observation_kwargs["output"] = clean["output"]
                if "metadata" in clean:
                    observation_kwargs["metadata"] = clean["metadata"]
                if observation_kwargs and hasattr(trace, "update"):
                    trace.update(**observation_kwargs)
                if "output" in clean and not trace_context.ended:
                    trace.end()
                    trace_context.ended = True
                return
            trace.update(**clean)
        except Exception:
            logger.exception("Failed to update Langfuse trace")

    def flush(self) -> None:
        if self.enabled and self.client:
            try:
                self.client.flush()
            except Exception:
                logger.exception("Failed to flush Langfuse")

    def _start_child_observation(
        self,
        trace_context: TraceContext,
        *,
        as_type: str,
        name: str,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
    ) -> Any | None:
        trace = trace_context.trace
        kwargs = {
            "name": name,
            "input": input,
            "metadata": metadata or {},
        }
        if model:
            kwargs["model"] = model
        if model_parameters:
            kwargs["model_parameters"] = sanitize_payload(model_parameters)
        if hasattr(trace, "start_observation"):
            return trace.start_observation(as_type=as_type, **kwargs)
        if as_type == "generation" and hasattr(trace, "generation"):
            return trace.generation(**kwargs)
        if hasattr(trace, "span"):
            return trace.span(**kwargs)
        return None

    @staticmethod
    def _update_observation(observation: Any, **kwargs: Any) -> None:
        clean = {key: sanitize_payload(value) for key, value in kwargs.items()}
        if hasattr(observation, "update"):
            observation.update(**clean)

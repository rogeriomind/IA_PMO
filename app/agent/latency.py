from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


_CURRENT_TRACKER: ContextVar["LatencyTracker | None"] = ContextVar(
    "agent_latency_tracker",
    default=None,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(start: float, finish: float) -> int:
    return max(0, int((finish - start) * 1000))


@dataclass
class LatencyTracker:
    marks: dict[str, str] = field(default_factory=dict)
    perf_marks: dict[str, float] = field(default_factory=dict)
    durations_ms: dict[str, int] = field(default_factory=dict)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    mcp_calls: list[dict[str, Any]] = field(default_factory=list)

    def mark(self, name: str) -> None:
        self.marks[name] = _utc_iso()
        self.perf_marks[name] = time.perf_counter()

    def mark_once(self, name: str) -> None:
        if name not in self.marks:
            self.mark(name)

    def finish_stage(self, stage: str) -> None:
        started_key = f"{stage}_started_at"
        finished_key = f"{stage}_finished_at"
        self.mark(finished_key)
        started = self.perf_marks.get(started_key)
        finished = self.perf_marks.get(finished_key)
        if started is not None and finished is not None:
            self.durations_ms[f"{stage}_ms"] = _duration_ms(started, finished)

    def add_duration(self, key: str, duration_ms: int) -> None:
        self.durations_ms[key] = self.durations_ms.get(key, 0) + max(0, duration_ms)

    def record_llm_call(self, *, name: str, duration_ms: int, success: bool) -> None:
        self.mark_once("llm_started_at")
        self.mark("llm_finished_at")
        self.add_duration("llm_ms", duration_ms)
        self.llm_calls.append(
            {
                "name": name,
                "duration_ms": max(0, duration_ms),
                "success": success,
            }
        )

    def record_mcp_call(
        self,
        *,
        tool_name: str,
        duration_ms: int,
        success: bool,
        retry_count: int,
        transport: str,
        tenant_id: str,
        request_id: str,
        correlation_id: str,
        error_code: str | None = None,
    ) -> None:
        self.mark_once("mcp_started_at")
        self.mark("mcp_finished_at")
        self.add_duration("mcp_ms", duration_ms)
        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "duration_ms": max(0, duration_ms),
            "success": success,
            "retry_count": max(0, retry_count),
            "transport": transport,
            "tenant_id": tenant_id,
            "request_id": request_id,
            "correlation_id": correlation_id,
        }
        if error_code:
            payload["error_code"] = error_code
        self.mcp_calls.append(payload)

    def snapshot(self, *, agent_total_ms: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {**self.marks}
        durations = dict(self.durations_ms)
        if agent_total_ms is not None:
            durations["agent_total_ms"] = max(0, agent_total_ms)
        for key in (
            "memory_load_ms",
            "routing_ms",
            "subgraph_ms",
            "llm_ms",
            "mcp_ms",
            "memory_persist_ms",
        ):
            durations.setdefault(key, 0)
        payload.update(durations)
        payload["llm_calls"] = list(self.llm_calls)
        payload["mcp_calls"] = list(self.mcp_calls)
        return payload


def set_latency_tracker(tracker: LatencyTracker | None):
    return _CURRENT_TRACKER.set(tracker)


def reset_latency_tracker(token) -> None:
    _CURRENT_TRACKER.reset(token)


def current_latency_tracker() -> LatencyTracker | None:
    return _CURRENT_TRACKER.get()


def mark_latency(name: str) -> None:
    tracker = current_latency_tracker()
    if tracker:
        tracker.mark(name)


def mark_latency_once(name: str) -> None:
    tracker = current_latency_tracker()
    if tracker:
        tracker.mark_once(name)


def finish_latency_stage(stage: str) -> None:
    tracker = current_latency_tracker()
    if tracker:
        tracker.finish_stage(stage)


def record_llm_call(*, name: str, duration_ms: int, success: bool) -> None:
    tracker = current_latency_tracker()
    if tracker:
        tracker.record_llm_call(name=name, duration_ms=duration_ms, success=success)


def record_mcp_call(
    *,
    tool_name: str,
    duration_ms: int,
    success: bool,
    retry_count: int,
    transport: str,
    tenant_id: str,
    request_id: str,
    correlation_id: str,
    error_code: str | None = None,
) -> None:
    tracker = current_latency_tracker()
    if tracker:
        tracker.record_mcp_call(
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            retry_count=retry_count,
            transport=transport,
            tenant_id=tenant_id,
            request_id=request_id,
            correlation_id=correlation_id,
            error_code=error_code,
        )

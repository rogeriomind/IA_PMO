from __future__ import annotations

from collections import Counter
from typing import Any


METRIC_NAMES = (
    "agent_requests_total",
    "agent_latency_ms",
    "mcp_calls_total",
    "agent_events_total",
    "agent_event_duration_seconds",
    "agent_flow_transitions_total",
    "agent_llm_calls_total",
    "agent_mcp_calls_total",
    "agent_confirmations_total",
    "agent_pending_actions_total",
    "agent_idempotency_hits_total",
    "agent_errors_total",
)


class AgentMetrics:
    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.observations: dict[str, list[float]] = {}

    def increment(self, name: str, **labels: Any) -> None:
        if name not in METRIC_NAMES:
            return
        self.counters[self._series_key(name, labels)] += 1

    def observe(self, name: str, value: float, **labels: Any) -> None:
        if name not in METRIC_NAMES:
            return
        self.observations.setdefault(self._series_key(name, labels), []).append(value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "observations": {
                key: {"count": len(values), "sum": sum(values), "last": values[-1]}
                for key, values in self.observations.items()
                if values
            },
        }

    @staticmethod
    def _series_key(name: str, labels: dict[str, Any]) -> str:
        label_key = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
        return f"{name}:{label_key}"

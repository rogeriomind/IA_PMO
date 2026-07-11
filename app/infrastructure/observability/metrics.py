from __future__ import annotations

from collections import Counter
from typing import Any


METRIC_NAMES = (
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

    def increment(self, name: str, **labels: Any) -> None:
        if name not in METRIC_NAMES:
            return
        label_key = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
        self.counters[f"{name}:{label_key}"] += 1

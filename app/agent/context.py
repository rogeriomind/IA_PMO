from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


@dataclass(frozen=True)
class ToolExecutionContext:
    request_id: str
    correlation_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    user_roles: list[str] = field(default_factory=list)
    intent: str = "unknown"
    approval_status: ApprovalStatus = "not_required"
    idempotency_key: str | None = None


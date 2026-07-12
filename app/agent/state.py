from __future__ import annotations

from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    request_id: str
    correlation_id: str
    thread_id: str

    tenant_id: str
    user_id: str
    user_roles: list[str]

    channel: str
    metadata: dict[str, Any]
    original_message: str
    normalized_message: str

    intent: str
    confidence: float
    entities: dict[str, Any]
    missing_fields: list[str]
    reasoning_summary: str | None

    selected_tool: str
    tool_input: dict[str, Any]
    tool_result: dict[str, Any]
    read_after_write_result: dict[str, Any] | list[Any] | str | None

    requires_confirmation: bool
    approval_status: Literal["not_required", "pending", "approved", "rejected"]

    action_preview: dict[str, Any]
    confirmation_id: str
    idempotency_key: str

    final_answer: str
    status: Literal["completed", "awaiting_confirmation", "rejected", "error"]
    data: dict[str, Any]

    route: str
    retry_count: int
    errors: list[dict[str, Any]]

    trace_id: str | None
    _trace: Any

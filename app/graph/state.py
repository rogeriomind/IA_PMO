from __future__ import annotations

from typing import Any, TypedDict

from app.schemas import Intent


class AgentState(TypedDict, total=False):
    conversation_id: str
    user_id: str
    channel: str
    message: str
    request_metadata: dict[str, Any]
    intent: Intent
    confidence: float
    entities: dict[str, Any]
    missing_fields: list[str]
    board_context: dict[str, Any] | list[Any] | str | None
    action: dict[str, Any] | None
    requires_confirmation: bool
    pending_action_id: str | None
    final_message: str
    trace_id: str | None
    route: str
    confirmed: bool
    pending_action: dict[str, Any] | None
    board_result: dict[str, Any] | list[Any] | str | None
    executed: bool
    error: str | None
    _trace: Any


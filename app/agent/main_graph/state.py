from __future__ import annotations

from typing import Any, TypedDict


class PMOAgentState(TypedDict, total=False):
    request_id: str
    correlation_id: str
    event_id: str

    thread_id: str
    tenant_id: str
    channel: str

    user_id: str
    user_name: str
    username: str | None
    user_roles: list[str]

    message_type: str
    message_text: str | None
    callback_data: str | None
    metadata: dict[str, Any]

    current_flow: str
    current_step: str
    previous_flow: str | None
    previous_step: str | None

    selected_menu: str | None
    selected_task_id: str | None
    selected_task_number: int | None
    task_selection_map: dict[str, str]

    create_draft: dict[str, Any]
    update_draft: dict[str, Any]
    proposed_operations: list[dict[str, Any]]

    pending_action_id: str | None
    confirmation_status: str | None

    board_result: dict[str, Any] | list[Any] | str | None
    final_message: str | None
    response_ui: dict[str, Any] | None

    response_status: str
    response_data: dict[str, Any]
    requires_confirmation: bool
    confirmation: dict[str, Any] | None
    api_response: dict[str, Any]

    route: str
    intent: str | None
    error_code: str | None
    error_message: str | None

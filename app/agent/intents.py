from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


IntentName = Literal[
    "task.search",
    "task.get",
    "task.create",
    "task.update",
    "task.move",
    "task.comment",
    "project.status",
    "project.blockers",
    "user.my_tasks",
    "help",
    "unknown",
]


READ_INTENTS = {
    "task.search",
    "task.get",
    "project.status",
    "project.blockers",
    "user.my_tasks",
}

WRITE_INTENTS = {
    "task.create",
    "task.update",
    "task.move",
    "task.comment",
}

INTENT_TO_TOOL = {
    "task.search": "board_search_tasks",
    "task.get": "board_get_task",
    "task.create": "board_create_task",
    "task.update": "board_update_task",
    "task.move": "board_move_task",
    "task.comment": "board_add_comment",
    "project.status": "board_get_project_status",
    "project.blockers": "board_list_blockers",
    "user.my_tasks": "board_list_my_tasks",
}


class AgentIntentClassification(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0, le=1)
    entities: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    reasoning_summary: str | None = None

    @field_validator("reasoning_summary")
    @classmethod
    def limit_reasoning_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()[:240]

    @field_validator("requires_confirmation")
    @classmethod
    def keep_confirmation_boolean(cls, value: bool) -> bool:
        return bool(value)


def is_write_intent(intent: str | None) -> bool:
    return bool(intent in WRITE_INTENTS)


def is_read_intent(intent: str | None) -> bool:
    return bool(intent in READ_INTENTS)


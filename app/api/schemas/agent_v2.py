from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentMessageType = Literal[
    "welcome",
    "text",
    "menu_selection",
    "task_selection",
    "confirmation",
    "cancel",
    "back",
    "reset",
]

AgentV2Status = Literal[
    "completed",
    "waiting_user_input",
    "awaiting_confirmation",
    "cancelled",
    "not_found",
    "validation_error",
    "unauthorized",
    "conflict",
    "degraded",
    "error",
]

AgentUIType = Literal["none", "inline_keyboard", "numbered_list", "confirmation"]


class AgentEventUser(BaseModel):
    id: str = Field(min_length=1)
    name: str | None = None
    username: str | None = None


class AgentEventContent(BaseModel):
    text: str | None = None
    callback_data: str | None = None


class AgentEventMetadata(BaseModel):
    chat_id: str | None = None
    message_id: str | None = None
    project_id: str | None = None
    timezone: str = "America/Sao_Paulo"
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentEventEnvelope(BaseModel):
    event_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    message_type: AgentMessageType
    user: AgentEventUser
    content: AgentEventContent = Field(default_factory=AgentEventContent)
    metadata: AgentEventMetadata = Field(default_factory=AgentEventMetadata)


class AgentUIOption(BaseModel):
    id: str
    label: str
    callback_data: str


class AgentUI(BaseModel):
    type: AgentUIType = "none"
    options: list[AgentUIOption] = Field(default_factory=list)


class AgentConfirmationPayload(BaseModel):
    id: str
    action_type: str
    preview: dict[str, Any] = Field(default_factory=dict)
    expires_at: str | None = None


class AgentV2Error(BaseModel):
    code: str
    message: str


class AgentV2Response(BaseModel):
    request_id: str
    correlation_id: str
    thread_id: str
    status: AgentV2Status
    flow: str
    step: str
    message: str
    ui: AgentUI = Field(default_factory=AgentUI)
    data: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation: AgentConfirmationPayload | None = None
    error: AgentV2Error | None = None


class AgentThreadSnapshot(BaseModel):
    thread_id: str
    tenant_id: str
    channel: str
    user_id: str
    user_name: str | None
    current_flow: str
    current_step: str
    state_summary: dict[str, Any] = Field(default_factory=dict)
    last_event_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None

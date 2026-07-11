from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStatus = Literal["completed", "awaiting_confirmation", "rejected", "error"]


class AgentMessageRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConfirmationRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    confirmation_id: str = Field(min_length=1)
    approved: bool
    message: str | None = None


class AgentConfirmationPayload(BaseModel):
    confirmation_id: str | None = None
    action: str | None = None
    preview: dict[str, Any] = Field(default_factory=dict)


class AgentErrorPayload(BaseModel):
    code: str
    message: str


class AgentV1Response(BaseModel):
    request_id: str
    thread_id: str
    status: AgentStatus
    intent: str | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    confirmation: AgentConfirmationPayload | None = None
    error: AgentErrorPayload | None = None


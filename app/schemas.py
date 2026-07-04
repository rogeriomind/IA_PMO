from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Intent(str, Enum):
    STATUS_BOARD = "STATUS_BOARD"
    TASK_CREATE = "TASK_CREATE"
    TASK_UPDATE = "TASK_UPDATE"
    TASK_MOVE = "TASK_MOVE"
    TASK_COMMENT = "TASK_COMMENT"
    BOARD_QUESTION = "BOARD_QUESTION"
    SMALLTALK = "SMALLTALK"
    UNKNOWN = "UNKNOWN"


class PendingActionStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class AgentInvokeRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentInvokeResponse(BaseModel):
    intent: Intent
    message: str
    requires_confirmation: bool = False
    pending_action_id: str | None = None
    action: AgentAction | None = None


class AgentConfirmRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    pending_action_id: str = Field(min_length=1)
    confirmed: bool


class AgentConfirmResponse(BaseModel):
    message: str
    executed: bool
    board_result: dict[str, Any] | list[Any] | str | None = None


class ExternalAgentProcessRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    user_id: str | None = None
    input_text: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class ExternalBoardAction(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ExternalAgentProcessResponse(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    response_text: str
    board_action: ExternalBoardAction
    missing_fields: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str
    model: str
    langfuse_enabled: bool
    mcp_loaded: bool
    checks: dict[str, Any] = Field(default_factory=dict)


class IntentClassification(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


class TaskEntities(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee: str | None = None
    priority: str | None = None
    due_date: str | None = None
    project: str | None = None
    status: str | None = None
    task_id: str | None = None
    task_query: str | None = None
    comment: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)

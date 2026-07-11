from __future__ import annotations

from pydantic import BaseModel, Field


class CreateTaskExtraction(BaseModel):
    title: str | None = None
    due_date: str | None = None
    assignee_name: str | None = None
    priority: str | None = None
    description: str | None = None
    project_id: str | None = None


class UpdateTaskExtraction(BaseModel):
    task_id: str | None = None
    task_number: int | None = None
    fields: dict[str, str | None] = Field(default_factory=dict)
    assignee_name: str | None = None
    comment: str | None = None


class DateExtraction(BaseModel):
    due_date: str | None = None


class AssigneeExtraction(BaseModel):
    assignee_name: str | None = None

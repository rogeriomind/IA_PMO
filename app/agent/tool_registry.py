from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Type

from pydantic import BaseModel, ConfigDict, Field


ToolType = Literal["read", "write"]


class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchTasksInput(StrictToolInput):
    search: str | None = None
    query: str | None = None
    project_id: str | None = None


class GetTaskInput(StrictToolInput):
    id: str | None = None
    task_id: str | None = None


class CreateTaskInput(StrictToolInput):
    title: str = Field(min_length=1)
    description: str | None = None
    assignee: str | None = None
    priority: str | None = None
    due_date: str | None = None
    dueDate: str | None = None
    project: str | None = None
    project_id: str | None = None
    status: str | None = None


class UpdateTaskInput(StrictToolInput):
    task_id: str | None = None
    id: str | None = None
    task_query: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class MoveTaskInput(StrictToolInput):
    task_id: str | None = None
    id: str | None = None
    task_query: str | None = None
    status: str = Field(min_length=1)


class AddCommentInput(StrictToolInput):
    task_id: str | None = None
    id: str | None = None
    task_query: str | None = None
    comment: str = Field(min_length=1)


class ProjectStatusInput(StrictToolInput):
    project_id: str | None = None
    query: str | None = None


class ListBlockersInput(StrictToolInput):
    project_id: str | None = None


class ListMyTasksInput(StrictToolInput):
    user_id: str = Field(min_length=1)
    project_id: str | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.2


@dataclass(frozen=True)
class ToolPolicy:
    tool_name: str
    required_permissions: set[str]
    requires_confirmation: bool


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    type: ToolType
    input_model: Type[StrictToolInput]
    timeout_seconds: float
    retry_policy: RetryPolicy
    requires_confirmation: bool
    required_permissions: set[str]
    mcp_tool_name: str
    allowed_intents: set[str]


class ToolRegistry:
    def __init__(
        self,
        *,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        read_retries: int,
    ) -> None:
        read_retry = RetryPolicy(max_attempts=max(1, read_retries + 1), backoff_seconds=0.2)
        no_retry = RetryPolicy(max_attempts=1, backoff_seconds=0.0)
        self._tools: dict[str, ToolSpec] = {
            "board_search_tasks": ToolSpec(
                name="board_search_tasks",
                description="Search board tasks by text query.",
                type="read",
                input_model=SearchTasksInput,
                timeout_seconds=read_timeout_seconds,
                retry_policy=read_retry,
                requires_confirmation=False,
                required_permissions={"board.read"},
                mcp_tool_name="board_search_tasks",
                allowed_intents={"task.search"},
            ),
            "board_get_task": ToolSpec(
                name="board_get_task",
                description="Read a single board task by id.",
                type="read",
                input_model=GetTaskInput,
                timeout_seconds=read_timeout_seconds,
                retry_policy=read_retry,
                requires_confirmation=False,
                required_permissions={"board.read"},
                mcp_tool_name="board_get_task",
                allowed_intents={"task.get"},
            ),
            "board_create_task": ToolSpec(
                name="board_create_task",
                description="Create a board task.",
                type="write",
                input_model=CreateTaskInput,
                timeout_seconds=write_timeout_seconds,
                retry_policy=no_retry,
                requires_confirmation=True,
                required_permissions={"board.write"},
                mcp_tool_name="board_create_task",
                allowed_intents={"task.create"},
            ),
            "board_update_task": ToolSpec(
                name="board_update_task",
                description="Update board task fields.",
                type="write",
                input_model=UpdateTaskInput,
                timeout_seconds=write_timeout_seconds,
                retry_policy=no_retry,
                requires_confirmation=True,
                required_permissions={"board.manage"},
                mcp_tool_name="board_update_task",
                allowed_intents={"task.update"},
            ),
            "board_move_task": ToolSpec(
                name="board_move_task",
                description="Move a board task to another status.",
                type="write",
                input_model=MoveTaskInput,
                timeout_seconds=write_timeout_seconds,
                retry_policy=no_retry,
                requires_confirmation=True,
                required_permissions={"board.manage"},
                mcp_tool_name="board_move_task",
                allowed_intents={"task.move"},
            ),
            "board_add_comment": ToolSpec(
                name="board_add_comment",
                description="Add a comment to a board task.",
                type="write",
                input_model=AddCommentInput,
                timeout_seconds=write_timeout_seconds,
                retry_policy=no_retry,
                requires_confirmation=True,
                required_permissions={"board.write"},
                mcp_tool_name="board_add_comment",
                allowed_intents={"task.comment"},
            ),
            "board_get_project_status": ToolSpec(
                name="board_get_project_status",
                description="Read project status summary.",
                type="read",
                input_model=ProjectStatusInput,
                timeout_seconds=read_timeout_seconds,
                retry_policy=read_retry,
                requires_confirmation=False,
                required_permissions={"board.read"},
                mcp_tool_name="board_get_project_status",
                allowed_intents={"project.status"},
            ),
            "board_list_blockers": ToolSpec(
                name="board_list_blockers",
                description="List project blockers.",
                type="read",
                input_model=ListBlockersInput,
                timeout_seconds=read_timeout_seconds,
                retry_policy=read_retry,
                requires_confirmation=False,
                required_permissions={"board.read"},
                mcp_tool_name="board_list_blockers",
                allowed_intents={"project.blockers"},
            ),
            "board_list_my_tasks": ToolSpec(
                name="board_list_my_tasks",
                description="List tasks assigned to the current user.",
                type="read",
                input_model=ListMyTasksInput,
                timeout_seconds=read_timeout_seconds,
                retry_policy=read_retry,
                requires_confirmation=False,
                required_permissions={"board.read"},
                mcp_tool_name="board_list_my_tasks",
                allowed_intents={"user.my_tasks"},
            ),
        }

    def get(self, tool_name: str) -> ToolSpec:
        return self._tools[tool_name]

    def has(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> set[str]:
        return set(self._tools)


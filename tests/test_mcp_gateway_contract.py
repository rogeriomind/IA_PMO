from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.agent.context import ToolExecutionContext
from app.agent.errors import MCPTimeoutError, ProjectContextMissingError
from app.agent.mcp_gateway import MCPGateway
from app.agent.tool_registry import ToolRegistry
from app.config import Settings
from app.storage.repository import PendingActionRepository


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    async def execute(self, tool_name, arguments, *, idempotency_key=None):
        self.calls.append((tool_name, arguments, idempotency_key))
        return {"ok": True, "arguments": arguments}


class FlakyWriteExecutor:
    def __init__(self):
        self.calls = []

    async def execute(self, tool_name, arguments, *, idempotency_key=None):
        self.calls.append((tool_name, arguments, idempotency_key))
        if len(self.calls) == 1:
            raise asyncio.TimeoutError()
        return {"id": "TASK-1", "project_id": arguments["project_id"]}


@pytest.fixture()
def repository(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'gateway.db'}", langfuse_enabled=False)
    repo = PendingActionRepository(settings)
    repo.init_db()
    return repo


def _gateway(repository, executor):
    return MCPGateway(
        registry=ToolRegistry(read_timeout_seconds=1, write_timeout_seconds=1, read_retries=0),
        executor=executor,
        repository=repository,
        result_max_chars=12000,
    )


def _context(*, intent="task.search", roles=None, approval_status="not_required"):
    return ToolExecutionContext(
        request_id="req-1",
        correlation_id="corr-1",
        thread_id="thread-1",
        tenant_id="tenant-a",
        user_id="user-1",
        api_version="v2",
        user_roles=roles or ["board.read", "board.write", "board.manage"],
        intent=intent,
        approval_status=approval_status,
    )


@pytest.mark.asyncio
async def test_gateway_enriches_read_arguments_with_tenant_and_project(repository):
    executor = RecordingExecutor()
    gateway = _gateway(repository, executor)

    await gateway.execute(
        tool_name="board_search_tasks",
        arguments={"search": "API", "project_id": "project-1"},
        context=_context(intent="task.search"),
    )

    assert executor.calls[0] == (
        "board_search_tasks",
        {"tenant_id": "tenant-a", "project_id": "project-1", "search": "API"},
        None,
    )


@pytest.mark.asyncio
async def test_gateway_blocks_project_scoped_tool_without_project(repository):
    executor = RecordingExecutor()
    gateway = _gateway(repository, executor)

    with pytest.raises(ProjectContextMissingError):
        await gateway.execute(
            tool_name="board_list_blockers",
            arguments={},
            context=_context(intent="project.blockers"),
        )

    assert executor.calls == []


@pytest.mark.asyncio
async def test_write_retry_reuses_same_idempotency_key(repository):
    executor = FlakyWriteExecutor()
    gateway = _gateway(repository, executor)
    context = _context(intent="task.create", approval_status="approved")

    with pytest.raises(MCPTimeoutError):
        await gateway.execute(
            tool_name="board_create_task",
            arguments={"project_id": "project-1", "title": "Homologar API"},
            context=context,
        )

    second = await gateway.execute(
        tool_name="board_create_task",
        arguments={"project_id": "project-1", "title": "Homologar API"},
        context=context,
    )

    assert second.status == "success"
    assert executor.calls[0][2] == executor.calls[1][2]
    assert executor.calls[0][1]["idempotency_key"] == executor.calls[1][1]["idempotency_key"]

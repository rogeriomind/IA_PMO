from __future__ import annotations

import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.mcp_gateway import ToolExecutionResult
from app.agent.subgraphs.status.nodes import StatusSubgraph
from app.config import Settings


class FakeSelectionService:
    def __init__(self) -> None:
        self.tasks = []

    async def replace_map(self, **kwargs):
        self.tasks = kwargs["tasks"]


class DelayedGateway:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls: list[str] = []

    async def execute(self, *, tool_name, arguments, context):
        self.calls.append(tool_name)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
            today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
            if tool_name == "board_list_my_tasks":
                result = [{"id": "TASK-TODAY", "title": "Revisar status", "due_date": today}]
            elif tool_name == "board_list_blockers":
                result = [{"id": "TASK-BLOCK", "title": "Resolver bloqueio", "status": "BLOCKED"}]
            else:
                result = {}
            return ToolExecutionResult(
                tool_name=tool_name,
                status="success",
                result=result,
                latency_ms=50,
            )
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_status_list_runs_independent_reads_in_parallel():
    gateway = DelayedGateway()
    selections = FakeSelectionService()
    subgraph = StatusSubgraph(gateway=gateway, selections=selections, settings=Settings())

    started = time.perf_counter()
    result = await subgraph._show_status_list(
        {
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "thread_id": "thread-1",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "user_roles": ["board.read"],
            "metadata": {"timezone": "America/Sao_Paulo"},
        }
    )
    elapsed = time.perf_counter() - started

    assert result["current_step"] == "waiting_status_action"
    assert gateway.max_active == 2
    assert elapsed < 0.09
    assert set(gateway.calls) == {"board_list_my_tasks", "board_list_blockers"}
    assert len(selections.tasks) == 2

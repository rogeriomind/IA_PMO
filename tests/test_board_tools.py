import pytest

from app.mcp.board_tools import BoardTools, normalize_priority, normalize_status
from app.mcp.client import MCPBoardClient


class FakeClient:
    def __init__(self):
        self.calls = []

    async def call_semantic_tool(self, internal_name, arguments, *, read_only, read_retries=None):
        self.calls.append((internal_name, arguments, read_only))
        if internal_name == "search_tasks":
            return {"tasks": [{"id": "TASK-1", "title": "Configurar lembrete automatico"}]}
        return arguments


def test_normalize_priority_to_board_enum():
    assert normalize_priority("baixa") == "LOW"
    assert normalize_priority("média") == "MEDIUM"
    assert normalize_priority("alta") == "HIGH"
    assert normalize_priority("urgente") == "CRITICAL"


def test_normalize_status_to_board_enum():
    assert normalize_status("em andamento") == "IN_PROGRESS"
    assert normalize_status("bloqueado") == "BLOCKED"


@pytest.mark.asyncio
async def test_create_task_normalizes_priority_before_mcp_call():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    result = await board_tools.create_task(
        tenant_id="tenant-a",
        project_id="project-1",
        payload={"title": "Teste", "priority": "baixa"},
        idempotency_key="idem-1",
    )

    assert result["priority"] == "LOW"
    assert fake_client.calls[0] == (
        "create_task",
        {
            "tenantId": "tenant-a",
            "projectId": "project-1",
            "idempotencyKey": "idem-1",
            "title": "Teste",
            "priority": "LOW",
        },
        False,
    )


@pytest.mark.asyncio
async def test_create_task_normalizes_assignee_alias_to_board_field():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    result = await board_tools.create_task(
        tenant_id="tenant-a",
        project_id="project-1",
        payload={"title": "Teste", "assignee": "board-user-1"},
        idempotency_key="idem-1",
    )

    assert result["assigneeId"] == "board-user-1"
    assert "assignee" not in result


@pytest.mark.asyncio
async def test_update_task_normalizes_due_date_before_mcp_call():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    result = await board_tools.update_task(
        tenant_id="tenant-a",
        project_id="project-1",
        task_id=None,
        task_query="Configurar lembrete automatico",
        fields={"due_date": "2026-07-04"},
        idempotency_key="idem-2",
    )

    assert result == {
        "tenantId": "tenant-a",
        "projectId": "project-1",
        "id": "TASK-1",
        "idempotencyKey": "idem-2",
        "dueDate": "2026-07-04",
    }
    assert fake_client.calls[0] == (
        "search_tasks",
        {"tenantId": "tenant-a", "projectId": "project-1", "search": "Configurar lembrete automatico"},
        True,
    )
    assert fake_client.calls[1][0] == "update_task"


@pytest.mark.asyncio
async def test_update_task_normalizes_assignee_id_alias_to_board_field():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    result = await board_tools.update_task(
        tenant_id="tenant-a",
        project_id="project-1",
        task_id="TASK-1",
        fields={"assignee_id": "board-user-1"},
        idempotency_key="idem-3",
    )

    assert result == {
        "tenantId": "tenant-a",
        "projectId": "project-1",
        "id": "TASK-1",
        "idempotencyKey": "idem-3",
        "assigneeId": "board-user-1",
    }


@pytest.mark.asyncio
async def test_task_identity_calls_send_board_id_contract():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    await board_tools.get_task(tenant_id="tenant-a", project_id="project-1", activity_id="TASK-1")
    await board_tools.move_task(
        tenant_id="tenant-a",
        project_id="project-1",
        task_id="TASK-1",
        status="em andamento",
        idempotency_key="idem-4",
    )
    await board_tools.add_comment(
        tenant_id="tenant-a",
        project_id="project-1",
        task_id="TASK-1",
        comment="feito",
        idempotency_key="idem-5",
    )

    assert fake_client.calls == [
        ("get_task", {"tenantId": "tenant-a", "projectId": "project-1", "id": "TASK-1"}, True),
        (
            "move_task",
            {
                "tenantId": "tenant-a",
                "projectId": "project-1",
                "id": "TASK-1",
                "status": "IN_PROGRESS",
                "idempotencyKey": "idem-4",
            },
            False,
        ),
        (
            "add_comment",
            {
                "tenantId": "tenant-a",
                "projectId": "project-1",
                "id": "TASK-1",
                "message": "feito",
                "idempotencyKey": "idem-5",
            },
            False,
        ),
    ]


@pytest.mark.asyncio
async def test_search_tasks_sends_tenant_and_project_contract():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    await board_tools.search_tasks(tenant_id="tenant-a", project_id="project-1", query="API")

    assert fake_client.calls[0] == (
        "search_tasks",
        {"tenantId": "tenant-a", "projectId": "project-1", "search": "API"},
        True,
    )


@pytest.mark.asyncio
async def test_project_reads_are_project_scoped():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    await board_tools.get_project_status(tenant_id="tenant-a", project_id="project-1")
    await board_tools.list_blockers(tenant_id="tenant-a", project_id="project-1")
    await board_tools.list_my_tasks(
        tenant_id="tenant-a",
        project_id="project-1",
        assignee_id="user-1",
        include_completed=False,
    )

    assert fake_client.calls == [
        ("get_project_status", {"tenantId": "tenant-a", "projectId": "project-1"}, True),
        ("list_blockers", {"tenantId": "tenant-a", "projectId": "project-1"}, True),
        (
            "list_my_tasks",
            {
                "tenantId": "tenant-a",
                "projectId": "project-1",
                "assigneeId": "user-1",
                "includeCompleted": False,
            },
            True,
        ),
    ]


def test_mcp_error_result_raises_runtime_error():
    class Result:
        def model_dump(self, mode="json"):
            return {
                "isError": True,
                "content": [{"type": "text", "text": "MCP error -32602: invalid"}],
            }

    with pytest.raises(RuntimeError, match="MCP error"):
        MCPBoardClient._normalize_result(Result())

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeBoardTools:
    def __init__(self):
        self.write_calls = []

    async def search_tasks(self, query: str, project_id: str | None = None):
        return [{"id": "TASK-1", "title": "revisar deploy"}]

    async def get_task(self, task_id: str):
        return {"id": task_id, "title": "revisar deploy", "status": "DONE"}

    async def get_project_status(self, project_id: str | None = None, query: str | None = None):
        return {"status": "em andamento", "open_tasks": 3}

    async def list_blockers(self, project_id: str | None = None):
        return []

    async def list_my_tasks(self, user_id: str, project_id: str | None = None):
        return [{"id": "TASK-1", "title": "minha tarefa"}]

    async def create_task(self, payload, idempotency_key=None):
        self.write_calls.append(("create", payload, idempotency_key))
        return {"id": "TASK-2", **payload}

    async def update_task(self, *, task_id, fields, task_query=None, idempotency_key=None):
        self.write_calls.append(("update", task_id, fields, task_query, idempotency_key))
        return {"id": task_id or "TASK-1", **fields}

    async def move_task(self, *, task_id, status, task_query=None, idempotency_key=None):
        self.write_calls.append(("move", task_id, status, task_query, idempotency_key))
        return {"id": task_id or "TASK-1", "status": status}

    async def add_comment(self, *, task_id, comment, task_query=None, idempotency_key=None):
        self.write_calls.append(("comment", task_id, comment, task_query, idempotency_key))
        return {"id": task_id or "TASK-1", "comment": comment}


@pytest.fixture()
def client(tmp_path: Path):
    doc_path = tmp_path / "board_pmo.md"
    doc_path.write_text(
        """
board_search_tasks
board_get_task
board_create_task
board_update_task
board_move_task
board_add_comment
board_get_project_status
board_list_blockers
board_list_my_tasks
""",
        encoding="utf-8",
    )
    settings = Settings(
        ai_provider="deepseek",
        deepseek_model="",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        mcp_board_doc_path=str(doc_path),
        langfuse_enabled=False,
    )
    fake_tools = FakeBoardTools()
    app = create_app(settings=settings, board_tools_override=fake_tools)
    with TestClient(app) as test_client:
        test_client.fake_tools = fake_tools
        yield test_client


def test_tool_registry_has_only_expected_board_tools(client):
    expected = {
        "board_search_tasks",
        "board_search_users",
        "board_get_task",
        "board_create_task",
        "board_update_task",
        "board_move_task",
        "board_add_comment",
        "board_get_project_status",
        "board_list_blockers",
        "board_list_my_tasks",
    }
    assert client.app.state.tool_registry.names() == expected


def test_v1_endpoints_are_deprecated_and_record_version_metrics(client):
    response = client.post(
        "/v1/agent/confirmations",
        headers={
            "X-Request-ID": "req-deprecated",
            "X-Correlation-ID": "corr-deprecated",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read,board.manage",
        },
        json={
            "thread_id": "porto:telegram:123",
            "confirmation_id": "missing",
            "approved": True,
            "message": "confirmo",
        },
    )

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert "Sunset" not in response.headers
    assert response.headers["Link"] == '</v2/agent/events>; rel="successor-version"'

    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v1/agent/messages"]["post"]["deprecated"] is True
    assert schema["paths"]["/v1/agent/confirmations"]["post"]["deprecated"] is True

    metrics = client.app.state.agent_metrics
    assert metrics.counters["agent_requests_total:api_version=v1"] == 1
    assert metrics.counters["agent_confirmations_total:api_version=v1"] == 1
    assert "agent_latency_ms:api_version=v1" in metrics.observations


def test_v1_my_tasks_uses_deterministic_router(client):
    response = client.post(
        "/v1/agent/messages",
        headers={
            "X-Request-ID": "req-1",
            "X-Correlation-ID": "corr-1",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read",
        },
        json={
            "thread_id": "porto:telegram:123",
            "message": "Minhas tarefas",
            "channel": "telegram",
            "metadata": {"project_id": "project-1"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-1"
    assert body["status"] == "completed"
    assert body["intent"] == "user.my_tasks"
    assert "minha tarefa" in body["message"]
    assert client.app.state.agent_metrics.counters["mcp_calls_total:api_version=v1"] == 1


def test_v1_write_requires_confirmation_before_mcp_write(client):
    response = client.post(
        "/v1/agent/messages",
        headers={
            "X-Request-ID": "req-2",
            "X-Correlation-ID": "corr-2",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read,board.manage",
        },
        json={
            "thread_id": "porto:telegram:123",
            "message": "Mova a tarefa TASK-123 para concluido",
            "channel": "telegram",
            "metadata": {"project_id": "project-1"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["intent"] == "task.move"
    assert body["confirmation"]["confirmation_id"]
    assert client.fake_tools.write_calls == []


def test_v1_confirmation_executes_write_once_and_read_after_write(client):
    invoke = client.post(
        "/v1/agent/messages",
        headers={
            "X-Request-ID": "req-3",
            "X-Correlation-ID": "corr-3",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read,board.manage",
        },
        json={
            "thread_id": "porto:telegram:123",
            "message": "Mova a tarefa TASK-123 para concluido",
            "channel": "telegram",
            "metadata": {"project_id": "project-1"},
        },
    ).json()

    confirmation_id = invoke["confirmation"]["confirmation_id"]
    confirm = client.post(
        "/v1/agent/confirmations",
        headers={
            "X-Request-ID": "req-4",
            "X-Correlation-ID": "corr-3",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read,board.manage",
        },
        json={
            "thread_id": "porto:telegram:123",
            "confirmation_id": confirmation_id,
            "approved": True,
            "message": "confirmo",
        },
    )

    assert confirm.status_code == 200
    body = confirm.json()
    assert body["status"] == "completed"
    assert body["data"]["result"]["status"] == "DONE"
    assert body["data"]["read_after_write"]["id"] == "TASK-123"
    assert len(client.fake_tools.write_calls) == 1


def test_v1_confirmation_rejects_ambiguous_approval_message(client):
    invoke = client.post(
        "/v1/agent/messages",
        headers={
            "X-Request-ID": "req-5",
            "X-Correlation-ID": "corr-5",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read,board.manage",
        },
        json={
            "thread_id": "porto:telegram:123",
            "message": "Mova a tarefa TASK-123 para concluido",
            "channel": "telegram",
            "metadata": {"project_id": "project-1"},
        },
    ).json()

    confirm = client.post(
        "/v1/agent/confirmations",
        headers={
            "X-Request-ID": "req-6",
            "X-Correlation-ID": "corr-5",
            "X-Tenant-ID": "porto",
            "X-User-ID": "user-1",
            "X-User-Roles": "board.read,board.manage",
        },
        json={
            "thread_id": "porto:telegram:123",
            "confirmation_id": invoke["confirmation"]["confirmation_id"],
            "approved": True,
            "message": "talvez",
        },
    )

    assert confirm.status_code == 200
    assert confirm.json()["status"] == "error"
    assert client.fake_tools.write_calls == []

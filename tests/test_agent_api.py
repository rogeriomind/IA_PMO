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

    async def get_project_status(self, project_id: str | None = None, query: str | None = None):
        return {"status": "em andamento", "open_tasks": 3, "blockers": []}

    async def list_blockers(self, project_id: str | None = None):
        return []

    async def list_my_tasks(self, user_id: str, project_id: str | None = None):
        return []

    async def create_task(self, payload, idempotency_key=None):
        self.write_calls.append(("create_task", payload, idempotency_key))
        return {"id": "TASK-2", **payload}

    async def update_task(self, *, task_id, fields, task_query=None, idempotency_key=None):
        self.write_calls.append(("update_task", task_id, fields, task_query, idempotency_key))
        return {"id": task_id or "TASK-1", "fields": fields}

    async def move_task(self, *, task_id, status, task_query=None, idempotency_key=None):
        self.write_calls.append(("move_task", task_id, status, task_query, idempotency_key))
        return {"id": task_id or "TASK-1", "status": status}

    async def add_comment(self, *, task_id, comment, task_query=None, idempotency_key=None):
        self.write_calls.append(("add_comment", task_id, comment, task_query, idempotency_key))
        return {"id": task_id or "TASK-1", "comment": comment}


@pytest.fixture()
def client(tmp_path: Path):
    doc_path = tmp_path / "board_pmo.md"
    doc_path.write_text(
        """
## Tools
- search_tasks: busca tarefas
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
        deepseek_model="deepseek-v4-flash",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        mcp_board_doc_path=str(doc_path),
        langfuse_enabled=False,
    )
    fake_tools = FakeBoardTools()
    app = create_app(settings=settings, board_tools_override=fake_tools)
    with TestClient(app) as test_client:
        test_client.fake_tools = fake_tools
        yield test_client


def test_task_create_without_title_asks_clarification(client):
    response = client.post(
        "/agent/invoke",
        json={
            "conversation_id": "whatsapp_1",
            "user_id": "1",
            "channel": "whatsapp",
            "message": "cria uma tarefa",
            "metadata": {"project_id": "pmo-agent"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "TASK_CREATE"
    assert body["requires_confirmation"] is False
    assert body["pending_action_id"] is None
    assert "titulo" in body["message"].casefold()


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "pmo-ai-agent-api"
    assert body["model"] == "deepseek-v4-flash"
    assert body["mcp_loaded"] is True
    assert body["checks"]["llm_provider"] == "deepseek"


def test_task_create_with_title_generates_pending_action_without_write(client):
    response = client.post(
        "/agent/invoke",
        json={
            "conversation_id": "whatsapp_1",
            "user_id": "1",
            "channel": "whatsapp",
            "message": "cria uma tarefa para revisar o deploy",
            "metadata": {"project_id": "pmo-agent"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "TASK_CREATE"
    assert body["requires_confirmation"] is True
    assert body["pending_action_id"]
    assert body["action"]["type"] == "create_task"
    assert client.fake_tools.write_calls == []


def test_confirm_true_executes_mocked_mcp_write(client):
    invoke = client.post(
        "/agent/invoke",
        json={
            "conversation_id": "whatsapp_2",
            "user_id": "2",
            "channel": "whatsapp",
            "message": "cria uma tarefa para revisar o deploy",
            "metadata": {"project_id": "pmo-agent"},
        },
    ).json()

    confirm = client.post(
        "/agent/confirm",
        json={
            "conversation_id": "whatsapp_2",
            "user_id": "2",
            "pending_action_id": invoke["pending_action_id"],
            "confirmed": True,
        },
    )

    assert confirm.status_code == 200
    body = confirm.json()
    assert body["executed"] is True
    assert body["board_result"]["id"] == "TASK-2"
    assert len(client.fake_tools.write_calls) == 1

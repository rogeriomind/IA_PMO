from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeBoardToolsV2:
    def __init__(self):
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        self.tasks = {
            "TASK-BLOCK": {
                "id": "TASK-BLOCK",
                "title": "Encontro de dados com CRM",
                "status": "BLOCKED",
                "due_date": (today - timedelta(days=1)).isoformat(),
                "priority": "HIGH",
            },
            "TASK-LATE": {
                "id": "TASK-LATE",
                "title": "Validar integracao do worker",
                "status": "IN_PROGRESS",
                "due_date": (today - timedelta(days=2)).isoformat(),
                "priority": "MEDIUM",
            },
            "TASK-TODAY": {
                "id": "TASK-TODAY",
                "title": "Revisar deploy da API",
                "status": "TODO",
                "due_date": today.isoformat(),
                "priority": "LOW",
            },
        }
        self.write_calls = []

    async def search_tasks(self, query: str, project_id: str | None = None):
        return [task for task in self.tasks.values() if query.casefold() in task["title"].casefold()]

    async def get_task(self, task_id: str):
        return self.tasks.get(task_id, {"id": task_id, "title": f"Tarefa {task_id}", "due_date": None})

    async def get_project_status(self, project_id: str | None = None, query: str | None = None):
        return {"status": "ok"}

    async def list_blockers(self, project_id: str | None = None):
        return [self.tasks["TASK-BLOCK"]]

    async def list_my_tasks(self, user_id: str, project_id: str | None = None):
        return list(self.tasks.values())

    async def create_task(self, payload, idempotency_key=None):
        self.write_calls.append(("create", payload, idempotency_key))
        created = {"id": "TASK-NEW", **payload}
        self.tasks["TASK-NEW"] = created
        return created

    async def update_task(self, *, task_id, fields, task_query=None, idempotency_key=None):
        self.write_calls.append(("update", task_id, fields, task_query, idempotency_key))
        self.tasks.setdefault(task_id, {"id": task_id, "title": task_id}).update(fields)
        return self.tasks[task_id]

    async def move_task(self, *, task_id, status, task_query=None, idempotency_key=None):
        self.write_calls.append(("move", task_id, status, task_query, idempotency_key))
        self.tasks.setdefault(task_id, {"id": task_id, "title": task_id})["status"] = status
        return self.tasks[task_id]

    async def add_comment(self, *, task_id, comment, task_query=None, idempotency_key=None):
        self.write_calls.append(("comment", task_id, comment, task_query, idempotency_key))
        return {"id": task_id, "comment": comment}


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
        agent_api_token="test-token",
    )
    fake_tools = FakeBoardToolsV2()
    app = create_app(settings=settings, board_tools_override=fake_tools)
    with TestClient(app) as test_client:
        test_client.fake_tools = fake_tools
        yield test_client


def _headers(roles: str = "board.read,board.write,board.manage"):
    return {
        "Authorization": "Bearer test-token",
        "X-Request-ID": "header-req",
        "X-Correlation-ID": "header-corr",
        "X-Tenant-ID": "default",
        "X-User-ID": "u1",
        "X-User-Roles": roles,
    }


def _event(event_id: str, message_type: str, *, text: str | None = None, callback_data: str | None = None):
    return {
        "event_id": event_id,
        "request_id": f"req-{event_id}",
        "correlation_id": f"corr-{event_id}",
        "thread_id": "default:telegram:123",
        "tenant_id": "default",
        "channel": "telegram",
        "message_type": message_type,
        "user": {"id": "u1", "name": "Rogerio", "username": "rogerio"},
        "content": {"text": text, "callback_data": callback_data},
        "metadata": {"chat_id": "123", "message_id": event_id, "project_id": "pmo", "timezone": "America/Sao_Paulo"},
    }


def test_v2_requires_agent_token(client):
    response = client.post("/v2/agent/events", json=_event("unauth", "welcome"))

    assert response.status_code == 401


def test_v2_welcome_with_name_returns_main_menu(client):
    response = client.post("/v2/agent/events", headers=_headers(), json=_event("welcome-1", "welcome"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_user_input"
    assert body["flow"] == "main_menu"
    assert "Rogerio" in body["message"]
    assert [option["callback_data"] for option in body["ui"]["options"]] == [
        "menu:status",
        "menu:create",
        "menu:update",
        "menu:questions",
    ]


def test_v2_status_lists_tasks_and_status_selection_enters_update(client):
    status_response = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("status-1", "menu_selection", callback_data="menu:status"),
    )

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["flow"] == "status"
    assert "Bloqueadas" in body["message"]
    assert "Atrasadas" in body["message"]
    assert "Para hoje" in body["message"]
    assert body["ui"]["options"][0]["callback_data"] == "status:task:1"

    detail = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("status-2", "task_selection", callback_data="status:task:1"),
    ).json()
    assert detail["step"] == "showing_task_detail"
    assert detail["data"]["task"]["id"] == "TASK-BLOCK"

    update = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("status-3", "menu_selection", callback_data="status:update_task"),
    ).json()
    assert update["flow"] == "task_update"
    assert update["status"] == "waiting_user_input"


def test_v2_create_extracts_fields_requires_confirmation_and_replays_event(client):
    create = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event(
            "create-1",
            "text",
            text="Criar atividade Revisar callbacks para hoje, prioridade alta. Precisamos validar os botoes.",
        ),
    )

    assert create.status_code == 200
    body = create.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["requires_confirmation"] is True
    assert body["confirmation"]["id"]
    assert client.fake_tools.write_calls == []

    replay = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event(
            "create-1",
            "text",
            text="Criar atividade Revisar callbacks para hoje, prioridade alta. Precisamos validar os botoes.",
        ),
    ).json()
    assert replay["data"]["replay"] is True

    confirmation_id = body["confirmation"]["id"]
    confirm = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("create-2", "confirmation", callback_data=f"confirmation:approve:{confirmation_id}"),
    ).json()
    assert confirm["status"] == "completed"
    assert client.fake_tools.write_calls[0][0] == "create"


def test_v2_update_from_list_creates_multiple_operations_and_confirms(client):
    client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("update-1", "menu_selection", callback_data="menu:update"),
    )
    client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("update-2", "menu_selection", callback_data="update:list_tasks"),
    )
    selected = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("update-3", "task_selection", callback_data="update:task:2"),
    ).json()
    assert selected["flow"] == "task_update"
    assert selected["step"] == "waiting_update_fields"

    preview = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("update-4", "text", text="Mude a data para amanha e adicione comentario aguardando retorno do CRM"),
    ).json()
    assert preview["status"] == "awaiting_confirmation"
    assert preview["data"]["operations_count"] == 2

    confirmation_id = preview["confirmation"]["id"]
    confirmed = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("update-5", "confirmation", callback_data=f"confirmation:approve:{confirmation_id}"),
    ).json()
    assert confirmed["status"] == "completed"
    assert [call[0] for call in client.fake_tools.write_calls[-2:]] == ["update", "comment"]

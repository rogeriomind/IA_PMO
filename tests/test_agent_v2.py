from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


ROGERIO_ID = "9b0dcbc7-e1d9-4c68-8de5-7a314b6d6c8f"


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
        self.read_calls = []
        self.write_calls = []
        self.users = [
            {"id": ROGERIO_ID, "name": "Rogerio", "email": "rogerio@pmo.local", "avatarUrl": None},
            {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "name": "Ana", "email": "ana@pmo.local", "avatarUrl": None},
        ]

    async def search_projects(self, tenant_id: str, query: str, limit: int = 10):
        self.read_calls.append(("search_projects", tenant_id, query))
        projects = [
            {"projectId": "consorcio", "name": "Consórcio", "portfolio": {"id": "portfolio-1"}},
            {"projectId": "fianca", "name": "Fiança", "portfolio": {"id": "portfolio-1"}},
            {"projectId": "crm-a", "name": "CRM", "portfolio": {"id": "portfolio-a"}},
            {"projectId": "crm-b", "name": "CRM", "portfolio": {"id": "portfolio-b"}},
        ]
        normalized = query.casefold().replace("ó", "o").replace("ç", "c").replace("ã", "a")
        return {
            "projects": [
                project
                for project in projects
                if normalized in project["name"].casefold().replace("ó", "o").replace("ç", "c").replace("ã", "a")
            ][:limit]
        }

    async def search_tasks(
        self,
        tenant_id: str | None = None,
        query: str = "",
        project_id: str | None = None,
    ):
        self.read_calls.append(("search_tasks", tenant_id, project_id, query))
        return [task for task in self.tasks.values() if query.casefold() in task["title"].casefold()]

    async def get_task(
        self,
        tenant_id: str | None = None,
        project_id: str | None = None,
        activity_id: str | None = None,
        task_id: str | None = None,
    ):
        task_id = activity_id or task_id
        self.read_calls.append(("get_task", tenant_id, project_id, task_id))
        task = self.tasks.get(task_id, {"id": task_id, "title": f"Tarefa {task_id}", "due_date": None})
        return {"task": task}

    async def get_project_status(self, tenant_id: str | None = None, project_id: str | None = None):
        self.read_calls.append(("project_status", tenant_id, project_id))
        return {"status": "ok"}

    async def list_blockers(
        self,
        tenant_id: str | None = None,
        project_id: str | None = None,
        assignee_id: str | None = None,
    ):
        self.read_calls.append(("blockers", tenant_id, project_id, assignee_id))
        return [self.tasks["TASK-BLOCK"]]

    async def search_users(
        self,
        tenant_id: str | None = None,
        query: str | None = None,
        limit: int = 20,
        project_id: str | None = None,
    ):
        self.read_calls.append(("users", tenant_id, project_id, query))
        if not query:
            return {"users": self.users[:limit]}
        normalized = query.casefold().replace("é", "e")
        return {
            "users": [
                user
                for user in self.users
                if normalized in user["name"].casefold() or normalized in user["email"].casefold()
            ][:limit]
        }

    async def list_my_tasks(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
        assignee_id: str | None = None,
        assignee_email: str | None = None,
        include_completed: bool | None = None,
    ):
        self.read_calls.append(("my_tasks", tenant_id, project_id, assignee_id, assignee_email, include_completed))
        return list(self.tasks.values())

    async def create_task(self, payload, tenant_id=None, project_id=None, idempotency_key=None):
        self.write_calls.append(("create", payload, idempotency_key))
        created = {"id": "TASK-NEW", **payload}
        self.tasks["TASK-NEW"] = created
        return created

    async def update_task(self, *, tenant_id=None, project_id=None, activity_id=None, task_id=None, fields, task_query=None, idempotency_key=None):
        task_id = activity_id or task_id
        self.write_calls.append(("update", tenant_id, project_id, task_id, fields, task_query, idempotency_key))
        self.tasks.setdefault(task_id, {"id": task_id, "title": task_id}).update(fields)
        return self.tasks[task_id]

    async def move_task(self, *, tenant_id=None, project_id=None, activity_id=None, task_id=None, status, task_query=None, idempotency_key=None):
        task_id = activity_id or task_id
        self.write_calls.append(("move", tenant_id, project_id, task_id, status, task_query, idempotency_key))
        self.tasks.setdefault(task_id, {"id": task_id, "title": task_id})["status"] = status
        return self.tasks[task_id]

    async def add_comment(self, *, tenant_id=None, project_id=None, activity_id=None, task_id=None, comment, task_query=None, idempotency_key=None):
        task_id = activity_id or task_id
        self.write_calls.append(("comment", tenant_id, project_id, task_id, comment, task_query, idempotency_key))
        return {"id": task_id, "project_id": project_id, "comment": comment}


@pytest.fixture()
def client(tmp_path: Path):
    doc_path = tmp_path / "board_pmo.md"
    doc_path.write_text(
        """
board_search_tasks
board_search_users
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
        DEEPSEEK_API_KEY="",
        DEEPSEEK_MODEL="",
        deepseek_model="",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        mcp_board_doc_path=str(doc_path),
        langfuse_enabled=False,
        agent_api_token="test-token",
        agent_default_user_roles="board.read,board.write,board.manage",
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


def _headers_without_roles():
    headers = _headers()
    headers.pop("X-User-Roles")
    return headers


def _event(
    event_id: str,
    message_type: str,
    *,
    text: str | None = None,
    callback_data: str | None = None,
    project_id: str | None = "pmo",
):
    metadata = {"chat_id": "123", "message_id": event_id, "timezone": "America/Sao_Paulo"}
    if project_id is not None:
        metadata["project_id"] = project_id
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
        "metadata": metadata,
    }


def test_v2_requires_agent_token(client):
    response = client.post("/v2/agent/events", json=_event("unauth", "welcome"))

    assert response.status_code == 401


def test_v2_official_endpoint_is_not_deprecated_and_records_metrics(client):
    response = client.post("/v2/agent/events", headers=_headers(), json=_event("official-1", "welcome"))

    assert response.status_code == 200
    assert "Deprecation" not in response.headers
    assert "Sunset" not in response.headers

    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v2/agent/events"]["post"].get("deprecated") is not True

    metrics = client.app.state.agent_metrics
    assert metrics.counters["agent_requests_total:api_version=v2"] == 1
    assert "agent_latency_ms:api_version=v2" in metrics.observations


def test_v2_welcome_with_name_returns_main_menu(client):
    response = client.post("/v2/agent/events", headers=_headers(), json=_event("welcome-1", "welcome"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_user_input"
    assert body["flow"] == "main_menu"
    assert "Rogerio" in body["message"]
    assert body["data"]["latency"]["agent_total_ms"] >= 0
    assert body["data"]["latency"]["request_received_at"]
    assert body["data"]["latency"]["response_built_at"]
    assert [option["callback_data"] for option in body["ui"]["options"]] == [
        "menu:status",
        "menu:create",
        "menu:update",
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
    assert body["ui"]["type"] == "inline_keyboard"
    assert body["ui"]["context_id"]
    assert body["ui"]["options"][0]["callback_data"] == "status:id:TASK-BLOCK"
    assert body["ui"]["options"][0]["label"] == "Ver 1"
    assert "status:update_task" not in [option["callback_data"] for option in body["ui"]["options"]]

    update_without_task = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("status-no-task-update", "menu_selection", callback_data="status:update_task"),
    ).json()
    assert update_without_task["flow"] == "task_update"
    assert update_without_task["step"] == "waiting_task_selection"

    detail = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("status-2", "task_selection", callback_data="status:id:TASK-BLOCK"),
    ).json()
    assert detail["step"] == "showing_task_detail"
    assert detail["data"]["task"]["id"] == "TASK-BLOCK"
    assert detail["data"]["task"]["assignee"] == {"id": None, "name": None}
    assert "Status: Bloqueada" in detail["message"]
    assert "Responsável: Não informado" in detail["message"]

    update = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("status-3", "menu_selection", callback_data="status:update_task"),
    ).json()
    assert update["flow"] == "task_update"
    assert update["status"] == "waiting_user_input"
    assert client.app.state.agent_metrics.counters["mcp_calls_total:api_version=v2"] >= 3


def test_v2_project_context_persists_and_status_uses_active_project(client):
    switch = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("project-context-1", "text", text="Vamos trabalhar no projeto Consórcio.", project_id=None),
    ).json()

    assert switch["status"] == "waiting_user_input"
    assert "Projeto ativo atualizado" in switch["message"]

    client.fake_tools.read_calls.clear()
    status = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("project-context-2", "menu_selection", callback_data="menu:status", project_id=None),
    ).json()

    assert status["flow"] == "status"
    assert ("my_tasks", "default", "consorcio", ROGERIO_ID, None, None) in client.fake_tools.read_calls
    assert ("blockers", "default", "consorcio", None) in client.fake_tools.read_calls


def test_v2_status_without_project_does_not_query_global_board(client):
    response = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("project-missing-1", "menu_selection", callback_data="menu:status", project_id=None),
    ).json()

    assert response["status"] == "waiting_user_input"
    assert response["error"]["code"] == "PROJECT_NOT_FOUND"
    assert not any(call[0] in {"my_tasks", "blockers"} for call in client.fake_tools.read_calls)


def test_v2_ambiguous_project_reference_asks_for_clarification(client):
    response = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("project-ambiguous-1", "text", text="Agora projeto CRM", project_id=None),
    ).json()

    assert response["status"] == "waiting_user_input"
    assert response["error"]["code"] == "PROJECT_AMBIGUOUS"
    assert "mais de um projeto" in response["message"].casefold()


def test_v2_greeting_and_explicit_intent_override_sticky_status_flow(client):
    client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("sticky-status-1", "menu_selection", callback_data="menu:status"),
    )

    greeting = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("sticky-status-2", "text", text="Ol\u00e1"),
    ).json()
    assert greeting["flow"] == "main_menu"
    assert [option["callback_data"] for option in greeting["ui"]["options"]] == [
        "menu:status",
        "menu:create",
        "menu:update",
    ]

    client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("sticky-status-3", "menu_selection", callback_data="menu:status"),
    )
    explicit_update = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("sticky-status-4", "text", text="atualizar atividade"),
    ).json()
    assert explicit_update["flow"] == "task_update"
    assert explicit_update["step"] == "waiting_task_selection"


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


def test_v2_create_resolves_assignee_to_board_uuid(client):
    create = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event(
            "create-assignee-1",
            "text",
            text="Criar atividade Testar o board para hoje, responsavel Rogerio.",
        ),
    ).json()

    assert create["status"] == "awaiting_confirmation"
    assert "Responsável: Rogerio" in create["message"]

    confirmation_id = create["confirmation"]["id"]
    confirm = client.post(
        "/v2/agent/events",
        headers=_headers(),
        json=_event("create-assignee-2", "confirmation", callback_data=f"confirmation:approve:{confirmation_id}"),
    ).json()

    assert confirm["status"] == "completed"
    _, payload, _ = client.fake_tools.write_calls[-1]
    assert payload["assigneeId"] == ROGERIO_ID
    assert payload["assigneeId"] != "u1"


def test_v2_confirmation_uses_default_roles_when_header_is_missing(client):
    create = client.post(
        "/v2/agent/events",
        headers=_headers_without_roles(),
        json=_event(
            "create-default-roles-1",
            "text",
            text="Criar atividade Testar permissoes padrao do board para hoje, prioridade baixa.",
        ),
    ).json()

    confirmation_id = create["confirmation"]["id"]
    confirm = client.post(
        "/v2/agent/events",
        headers=_headers_without_roles(),
        json=_event(
            "create-default-roles-2",
            "confirmation",
            callback_data=f"confirmation:approve:{confirmation_id}",
        ),
    ).json()

    assert confirm["status"] == "completed"
    assert client.fake_tools.write_calls[-1][0] == "create"


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

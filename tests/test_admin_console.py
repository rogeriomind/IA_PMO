from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeBoardTools:
    async def search_tasks(self, query: str, project_id: str | None = None):
        return []


@pytest.fixture()
def client(tmp_path: Path):
    doc_path = tmp_path / "board_pmo.md"
    doc_path.write_text(
        "\n".join(
            [
                "board_search_tasks",
                "board_get_task",
                "board_create_task",
                "board_update_task",
                "board_move_task",
                "board_add_comment",
                "board_get_project_status",
                "board_list_blockers",
                "board_list_my_tasks",
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        ai_provider="deepseek",
        deepseek_model="deepseek-v4-flash",
        database_url=f"sqlite:///{tmp_path / 'admin-console.db'}",
        encryption_key="test-admin-console-master-key",
        mcp_board_doc_path=str(doc_path),
        langfuse_enabled=False,
        agent_api_token="test-token",
        agent_default_user_roles="board.read",
    )
    app = create_app(settings=settings, board_tools_override=FakeBoardTools())
    with TestClient(app) as test_client:
        yield test_client


def _headers(roles: str = "agent.admin", tenant_id: str = "default") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-token",
        "X-Tenant-ID": tenant_id,
        "X-User-ID": "rogerio",
        "X-User-Roles": roles,
    }


def test_admin_console_requires_admin_role(client: TestClient):
    response = client.get("/admin/v1/dashboard", headers=_headers("board.read"))

    assert response.status_code == 403


def test_admin_console_me_and_dashboard_are_available(client: TestClient):
    me = client.get("/admin/v1/me", headers=_headers())
    dashboard = client.get("/admin/v1/dashboard", headers=_headers())

    assert me.status_code == 200
    assert me.json()["role"] == "Administrador"
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert {kpi["id"] for kpi in body["kpis"]} == {"conversations", "pending", "resolution", "response"}
    assert body["pendingActions"] == []
    assert body["conversationsByDay"]


def test_admin_console_configuration_masks_secrets(client: TestClient):
    secret = client.post(
        "/admin/v1/tenants/default/secrets/openai_key",
        headers=_headers("tenant.admin"),
        json={"value": "sk-live-secret-value"},
    )
    assert secret.status_code == 200

    response = client.get("/admin/v1/configuration", headers=_headers("tenant.admin"))

    assert response.status_code == 200
    body = response.json()
    assert "sk-live-secret-value" not in str(body)
    assert body["company"]["slug"] == "default"
    assert body["security"]["secrets"][0].startswith("openai_key=********")

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
    doc_path.write_text("board_search_tasks\n", encoding="utf-8")
    settings = Settings(
        ai_provider="deepseek",
        deepseek_model="",
        database_url=f"sqlite:///{tmp_path / 'tenant.db'}",
        encryption_key="test-control-plane-master-key",
        mcp_board_doc_path=str(doc_path),
        langfuse_enabled=False,
        agent_api_token="test-token",
        agent_default_user_roles="board.read",
    )
    app = create_app(settings=settings, board_tools_override=FakeBoardTools())
    with TestClient(app) as test_client:
        yield test_client


def _headers(roles: str, tenant_id: str = "default") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-token",
        "X-Tenant-ID": tenant_id,
        "X-User-ID": "admin-user",
        "X-User-Roles": roles,
    }


def test_platform_admin_creates_tenant_and_publishes_configuration(client: TestClient):
    created = client.post(
        "/admin/v1/tenants",
        headers=_headers("platform.admin"),
        json={"slug": "acme-corp", "name": "Acme Corp", "status": "ACTIVE"},
    )
    assert created.status_code == 201
    tenant_id = created.json()["id"]

    ai_config = client.put(
        f"/admin/v1/tenants/{tenant_id}/ai-config",
        headers=_headers("platform.admin"),
        json={"provider": "openai", "model": "gpt-5.5-nano", "temperature": 0.1},
    )
    assert ai_config.status_code == 200
    assert ai_config.json()["version"] == 1

    published = client.post(
        f"/admin/v1/tenants/{tenant_id}/publish",
        headers=_headers("platform.admin"),
        json={"reason": "initial config"},
    )
    assert published.status_code == 200
    assert published.json()["version"] == 1
    assert published.json()["status"] == "PUBLISHED"

    updated = client.put(
        f"/admin/v1/tenants/{tenant_id}/ai-config",
        headers=_headers("platform.admin"),
        json={"provider": "deepseek", "model": "deepseek-v4-flash", "temperature": 0.2},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    rollback = client.post(
        f"/admin/v1/tenants/{tenant_id}/versions/1/rollback",
        headers=_headers("platform.admin"),
        json={"reason": "restore initial config"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["version"] == 2

    restored = client.get(f"/admin/v1/tenants/{tenant_id}/ai-config", headers=_headers("platform.admin"))
    assert restored.json()["provider"] == "openai"
    assert restored.json()["model"] == "gpt-5.5-nano"


def test_tenant_admin_cannot_access_another_tenant(client: TestClient):
    tenant_a = client.post(
        "/admin/v1/tenants",
        headers=_headers("platform.admin"),
        json={"slug": "tenant-a", "name": "Tenant A", "status": "ACTIVE"},
    ).json()["id"]
    tenant_b = client.post(
        "/admin/v1/tenants",
        headers=_headers("platform.admin"),
        json={"slug": "tenant-b", "name": "Tenant B", "status": "ACTIVE"},
    ).json()["id"]

    own = client.get(f"/admin/v1/tenants/{tenant_a}", headers=_headers("tenant.admin", tenant_id=tenant_a))
    other = client.get(f"/admin/v1/tenants/{tenant_b}", headers=_headers("tenant.admin", tenant_id=tenant_a))

    assert own.status_code == 200
    assert other.status_code == 403


def test_secret_is_encrypted_and_masked(client: TestClient):
    created = client.post(
        "/admin/v1/tenants",
        headers=_headers("platform.admin"),
        json={"slug": "secret-tenant", "name": "Secret Tenant", "status": "ACTIVE"},
    )
    tenant_id = created.json()["id"]

    secret = client.post(
        f"/admin/v1/tenants/{tenant_id}/secrets/telegram_token",
        headers=_headers("tenant.admin", tenant_id=tenant_id),
        json={"value": "super-secret-token-1234"},
    )

    assert secret.status_code == 200
    body = secret.json()
    assert body["configured"] is True
    assert body["masked"].endswith("1234")
    assert "super-secret-token" not in str(body)


def test_tenant_manager_cannot_change_secret(client: TestClient):
    response = client.post(
        "/admin/v1/tenants/default/secrets/telegram_token",
        headers=_headers("tenant.admin,tenant.manager", tenant_id="default"),
        json={"value": "secret"},
    )

    assert response.status_code == 403

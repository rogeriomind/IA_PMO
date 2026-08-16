from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from app.storage.repository import AgentThreadModel, Base, PendingActionModel
from app.tenancy.control_plane import TenantBase, TenantModel
from scripts.migrate_sqlite_to_postgres import MigrationError, migrate


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _init_db(path: Path):
    engine = create_engine(_sqlite_url(path), connect_args={"check_same_thread": False})
    TenantBase.metadata.create_all(engine)
    Base.metadata.create_all(engine)
    return engine


def _seed_source(path: Path) -> None:
    engine = _init_db(path)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            TenantModel.__table__.insert().values(
                id="default",
                slug="default",
                name="Default",
                status="ACTIVE",
                timezone="America/Sao_Paulo",
                locale="pt-BR",
                environment="production",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            AgentThreadModel.__table__.insert().values(
                id="thread-row-1",
                thread_id="default:telegram:1",
                tenant_id="default",
                channel="telegram",
                user_id="u1",
                user_name="Rogerio",
                current_flow="status",
                current_step="waiting_status_action",
                state_summary={"task_selection_map": {"1": "task-1"}},
                last_event_id="event-1",
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )
        connection.execute(
            PendingActionModel.__table__.insert().values(
                id="pending-1",
                conversation_id="default:telegram:1",
                tenant_id="default",
                thread_id="default:telegram:1",
                user_id="u1",
                request_id="req-1",
                correlation_id="corr-1",
                action_type="task.update",
                tool_name="board_update_task",
                operations=[{"tool_name": "board_update_task"}],
                payload={"task_id": "task-1"},
                preview={"task_title": "Revisar status"},
                action_payload={"tool_input": {"task_id": "task-1"}},
                status="pending",
                created_at=now,
                updated_at=now,
                expires_at=now,
                confirmed_at=None,
                executed_at=None,
                result=None,
                error=None,
                version=1,
            )
        )
    engine.dispose()


def test_migrate_sqlite_preserves_ids_json_and_counts(tmp_path: Path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _seed_source(source)

    result = migrate(
        sqlite_url=_sqlite_url(source),
        target_url=_sqlite_url(target),
        init_schema=True,
        expected_threads=1,
        expected_pending_action_id="pending-1",
    )

    assert result["source_counts"]["agent_threads"] == 1
    assert result["target_after"]["pending_actions"] == 1

    engine = create_engine(_sqlite_url(target), connect_args={"check_same_thread": False})
    with engine.connect() as connection:
        thread = connection.execute(select(AgentThreadModel.__table__)).mappings().one()
        pending = connection.execute(select(PendingActionModel.__table__)).mappings().one()
    engine.dispose()

    assert thread["id"] == "thread-row-1"
    assert thread["state_summary"] == {"task_selection_map": {"1": "task-1"}}
    assert pending["id"] == "pending-1"
    assert pending["payload"] == {"task_id": "task-1"}


def test_migrate_sqlite_is_idempotent_by_primary_key(tmp_path: Path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _seed_source(source)

    migrate(sqlite_url=_sqlite_url(source), target_url=_sqlite_url(target), init_schema=True)
    second = migrate(
        sqlite_url=_sqlite_url(source),
        target_url=_sqlite_url(target),
        init_schema=True,
        idempotent=True,
    )

    assert second["copied"]["agent_threads"] == 0
    assert second["skipped"]["agent_threads"] == 1
    assert second["target_after"]["agent_threads"] == 1


def test_migrate_sqlite_rolls_back_on_insert_conflict(tmp_path: Path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _seed_source(source)
    engine = _init_db(target)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            AgentThreadModel.__table__.insert().values(
                id="thread-row-1",
                thread_id="other-thread",
                tenant_id="default",
                channel="telegram",
                user_id="u1",
                user_name=None,
                current_flow="main_menu",
                current_step="waiting_menu_selection",
                state_summary={},
                last_event_id=None,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )
    engine.dispose()

    with pytest.raises(MigrationError):
        migrate(
            sqlite_url=_sqlite_url(source),
            target_url=_sqlite_url(target),
            init_schema=True,
            require_empty=False,
        )

    engine = create_engine(_sqlite_url(target), connect_args={"check_same_thread": False})
    with engine.connect() as connection:
        tenants = connection.scalar(select(TenantModel.__table__.c.id))
        threads = connection.execute(select(AgentThreadModel.__table__.c.thread_id)).scalars().all()
    engine.dispose()

    assert tenants is None
    assert threads == ["other-thread"]

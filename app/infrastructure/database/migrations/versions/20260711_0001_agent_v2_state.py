"""agent v2 conversational state

Revision ID: 20260711_0001
Revises:
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260711_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "pending_actions" not in tables:
        op.create_table(
            "pending_actions",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("conversation_id", sa.String(length=255), nullable=False),
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
            sa.Column("thread_id", sa.String(length=255), nullable=True),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("request_id", sa.String(length=255), nullable=True),
            sa.Column("correlation_id", sa.String(length=255), nullable=True),
            sa.Column("action_type", sa.String(length=80), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=True),
            sa.Column("operations", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("preview", sa.JSON(), nullable=True),
            sa.Column("action_payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    else:
        existing_columns = {column["name"] for column in inspector.get_columns("pending_actions")}
        for column in _pending_action_new_columns():
            if column.name not in existing_columns:
                op.add_column("pending_actions", column)

    _create_index_if_missing("ix_pending_actions_conversation_id", "pending_actions", ["conversation_id"])
    _create_index_if_missing("ix_pending_actions_tenant_id", "pending_actions", ["tenant_id"])
    _create_index_if_missing("ix_pending_actions_thread_id", "pending_actions", ["thread_id"])
    _create_index_if_missing("ix_pending_actions_user_id", "pending_actions", ["user_id"])
    _create_index_if_missing("ix_pending_actions_request_id", "pending_actions", ["request_id"])
    _create_index_if_missing("ix_pending_actions_correlation_id", "pending_actions", ["correlation_id"])
    _create_index_if_missing("ix_pending_actions_tool_name", "pending_actions", ["tool_name"])
    _create_index_if_missing("ix_pending_actions_status", "pending_actions", ["status"])
    _create_index_if_missing("ix_pending_actions_expires_at", "pending_actions", ["expires_at"])

    if "agent_idempotency_records" not in tables:
        op.create_table(
            "agent_idempotency_records",
            sa.Column("key", sa.String(length=128), primary_key=True),
            sa.Column("tenant_id", sa.String(length=255), nullable=False),
            sa.Column("request_id", sa.String(length=255), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=False),
            sa.Column("arguments_hash", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        _create_index_if_missing("ix_agent_idempotency_records_tenant_id", "agent_idempotency_records", ["tenant_id"])
        _create_index_if_missing("ix_agent_idempotency_records_request_id", "agent_idempotency_records", ["request_id"])
        _create_index_if_missing("ix_agent_idempotency_records_tool_name", "agent_idempotency_records", ["tool_name"])
        _create_index_if_missing("ix_agent_idempotency_records_status", "agent_idempotency_records", ["status"])

    if "agent_tool_execution_audit" not in tables:
        op.create_table(
            "agent_tool_execution_audit",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("request_id", sa.String(length=255), nullable=False),
            sa.Column("correlation_id", sa.String(length=255), nullable=False),
            sa.Column("thread_id", sa.String(length=255), nullable=False),
            sa.Column("tenant_id", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("intent", sa.String(length=80), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=False),
            sa.Column("tool_type", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            sa.Column("arguments", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    _create_agent_threads()
    _create_agent_task_selection_maps()
    _create_agent_drafts()
    _create_agent_events()
    _create_agent_graph_checkpoints()


def downgrade() -> None:
    op.drop_table("agent_graph_checkpoints")
    op.drop_table("agent_events")
    op.drop_table("agent_drafts")
    op.drop_table("agent_task_selection_maps")
    op.drop_table("agent_threads")


def _pending_action_new_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("operations", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("preview", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def _create_agent_threads() -> None:
    op.create_table(
        "agent_threads",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("user_name", sa.String(length=255), nullable=True),
        sa.Column("current_flow", sa.String(length=80), nullable=False),
        sa.Column("current_step", sa.String(length=120), nullable=False),
        sa.Column("state_summary", sa.JSON(), nullable=False),
        sa.Column("last_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "thread_id", name="uq_agent_threads_tenant_thread"),
    )


def _create_agent_task_selection_maps() -> None:
    op.create_table(
        "agent_task_selection_maps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("context", sa.String(length=80), nullable=False),
        sa.Column("selection_number", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("task_title", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "thread_id",
            "user_id",
            "context",
            "selection_number",
            name="uq_agent_task_selection_number",
        ),
    )


def _create_agent_drafts() -> None:
    op.create_table(
        "agent_drafts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("draft_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_agent_events() -> None:
    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("message_type", sa.String(length=80), nullable=False),
        sa.Column("flow", sa.String(length=80), nullable=True),
        sa.Column("step", sa.String(length=120), nullable=True),
        sa.Column("input_payload_sanitized", sa.JSON(), nullable=False),
        sa.Column("output_payload_sanitized", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_agent_events_event_id"),
    )


def _create_agent_graph_checkpoints() -> None:
    op.create_table(
        "agent_graph_checkpoints",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "thread_id", name="uq_agent_graph_checkpoint"),
    )


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns)

"""mcp latency audit metadata

Revision ID: 20260815_0003
Revises: 20260712_0002
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260815_0003"
down_revision = "20260712_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _has_table("agent_tool_execution_audit"):
        return
    columns = _columns("agent_tool_execution_audit")
    if "retry_count" not in columns:
        op.add_column(
            "agent_tool_execution_audit",
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "transport" not in columns:
        op.add_column(
            "agent_tool_execution_audit",
            sa.Column("transport", sa.String(length=40), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("agent_tool_execution_audit"):
        return
    columns = _columns("agent_tool_execution_audit")
    if "transport" in columns:
        op.drop_column("agent_tool_execution_audit", "transport")
    if "retry_count" in columns:
        op.drop_column("agent_tool_execution_audit", "retry_count")


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in set(sa.inspect(bind).get_table_names())


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}

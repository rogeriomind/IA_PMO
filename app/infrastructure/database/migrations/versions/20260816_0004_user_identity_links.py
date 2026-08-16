"""user identity links

Revision ID: 20260816_0004
Revises: 20260815_0003
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260816_0004"
down_revision = "20260815_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _has_table("agent_user_identity_links"):
        return

    op.create_table(
        "agent_user_identity_links",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("board_user_id", sa.String(length=255), nullable=False),
        sa.Column("board_user_name", sa.String(length=255), nullable=True),
        sa.Column("board_user_email", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "channel",
            "provider_user_id",
            name="uq_agent_user_identity_link_provider",
        ),
    )
    op.create_index("ix_agent_user_identity_links_tenant_id", "agent_user_identity_links", ["tenant_id"])
    op.create_index("ix_agent_user_identity_links_channel", "agent_user_identity_links", ["channel"])
    op.create_index(
        "ix_agent_user_identity_links_provider_user_id",
        "agent_user_identity_links",
        ["provider_user_id"],
    )
    op.create_index("ix_agent_user_identity_links_board_user_id", "agent_user_identity_links", ["board_user_id"])


def downgrade() -> None:
    if _has_table("agent_user_identity_links"):
        op.drop_table("agent_user_identity_links")


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in set(sa.inspect(bind).get_table_names())

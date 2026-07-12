"""tenant control plane

Revision ID: 20260712_0002
Revises: 20260711_0001
Create Date: 2026-07-12
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

revision = "20260712_0002"
down_revision = "20260711_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _has_table("tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("legal_name", sa.String(length=255), nullable=True),
            sa.Column("document", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("timezone", sa.String(length=80), nullable=False),
            sa.Column("locale", sa.String(length=20), nullable=False),
            sa.Column("environment", sa.String(length=40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        )
        op.create_index("ix_tenants_slug", "tenants", ["slug"])
        op.create_index("ix_tenants_status", "tenants", ["status"])
        _insert_default_tenant()

    _create_table_if_missing(
        "tenant_branding",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("favicon_url", sa.String(length=500), nullable=True),
        sa.Column("primary_color", sa.String(length=24), nullable=True),
        sa.Column("secondary_color", sa.String(length=24), nullable=True),
        sa.Column("assistant_name", sa.String(length=120), nullable=True),
        sa.Column("assistant_tone", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_branding_tenant"),
    )
    _create_table_if_missing(
        "tenant_users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "external_user_id", name="uq_tenant_users_external_id"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_tenant_users_email"),
    )
    _create_table_if_missing(
        "tenant_user_roles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("tenant_users.id"), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "role", name="uq_tenant_user_roles_role"),
    )
    _create_table_if_missing(
        "tenant_channels",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("channel_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("external_identifier", sa.String(length=255), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("secret_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "channel_type", "external_identifier", name="uq_tenant_channel_identifier"),
    )
    _create_table_if_missing(
        "tenant_ai_configs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("top_p", sa.Float(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("confidence_threshold", sa.Float(), nullable=False),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_ai_configs_tenant"),
    )
    _create_table_if_missing(
        "tenant_agent_policies",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("require_write_confirmation", sa.Boolean(), nullable=False),
        sa.Column("max_message_chars", sa.Integer(), nullable=False),
        sa.Column("memory_retention_days", sa.Integer(), nullable=False),
        sa.Column("session_ttl_minutes", sa.Integer(), nullable=False),
        sa.Column("pending_action_ttl_minutes", sa.Integer(), nullable=False),
        sa.Column("max_ui_options", sa.Integer(), nullable=False),
        sa.Column("allowed_intents", sa.JSON(), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_agent_policies_tenant"),
    )
    _create_table_if_missing(
        "tenant_integrations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("integration_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("transport", sa.String(length=80), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("secret_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "integration_type", "base_url", name="uq_tenant_integration_target"),
    )
    _create_table_if_missing(
        "tenant_rate_limits",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("max_messages", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("debounce_seconds", sa.Integer(), nullable=False),
        sa.Column("worker_retry_attempts", sa.Integer(), nullable=False),
        sa.Column("worker_lock_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_rate_limits_tenant"),
    )
    _create_table_if_missing(
        "tenant_secrets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("secret_name", sa.String(length=120), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("encryption_version", sa.String(length=40), nullable=False),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "secret_name", name="uq_tenant_secrets_name"),
    )
    _create_table_if_missing(
        "tenant_feature_flags",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("feature_name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "feature_name", name="uq_tenant_feature_flags_name"),
    )
    _create_table_if_missing(
        "tenant_configuration_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("author_user_id", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "version", name="uq_tenant_configuration_version"),
    )

    for table, columns in {
        "tenant_branding": ["tenant_id"],
        "tenant_users": ["tenant_id", "status"],
        "tenant_user_roles": ["tenant_id", "user_id", "role"],
        "tenant_channels": ["tenant_id", "channel_type", "status"],
        "tenant_ai_configs": ["tenant_id", "status"],
        "tenant_agent_policies": ["tenant_id"],
        "tenant_integrations": ["tenant_id", "integration_type", "status"],
        "tenant_rate_limits": ["tenant_id"],
        "tenant_secrets": ["tenant_id", "secret_name"],
        "tenant_feature_flags": ["tenant_id", "feature_name"],
        "tenant_configuration_versions": ["tenant_id", "status"],
    }.items():
        for column in columns:
            _create_index_if_missing(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in [
        "tenant_configuration_versions",
        "tenant_feature_flags",
        "tenant_secrets",
        "tenant_rate_limits",
        "tenant_integrations",
        "tenant_agent_policies",
        "tenant_ai_configs",
        "tenant_channels",
        "tenant_user_roles",
        "tenant_users",
        "tenant_branding",
        "tenants",
    ]:
        if _has_table(table):
            op.drop_table(table)


def _has_table(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _create_table_if_missing(table_name: str, *columns: sa.Column | sa.Constraint) -> None:
    if not _has_table(table_name):
        op.create_table(table_name, *columns)


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns)


def _insert_default_tenant() -> None:
    tenants = sa.table(
        "tenants",
        sa.column("id", sa.String),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("status", sa.String),
        sa.column("timezone", sa.String),
        sa.column("locale", sa.String),
        sa.column("environment", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    now = datetime.now(timezone.utc)
    try:
        op.get_bind().execute(
            tenants.insert().values(
                id="default",
                slug="default",
                name="Default Tenant",
                status="ACTIVE",
                timezone="America/Sao_Paulo",
                locale="pt-BR",
                environment="production",
                created_at=now,
                updated_at=now,
            )
        )
    except IntegrityError:
        pass

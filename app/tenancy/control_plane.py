from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Settings
from app.tenancy.security import SecretEncryptionService


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ControlPlaneError(RuntimeError):
    pass


class TenantNotFoundError(ControlPlaneError):
    pass


class TenantConflictError(ControlPlaneError):
    pass


class TenantBase(DeclarativeBase):
    pass


class TenantModel(TenantBase):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    document: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Sao_Paulo")
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="pt-BR")
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="production")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantBrandingModel(TenantBase):
    __tablename__ = "tenant_branding"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_branding_tenant"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    favicon_url: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str | None] = mapped_column(String(24))
    secondary_color: Mapped[str | None] = mapped_column(String(24))
    assistant_name: Mapped[str | None] = mapped_column(String(120))
    assistant_tone: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantUserModel(TenantBase):
    __tablename__ = "tenant_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_user_id", name="uq_tenant_users_external_id"),
        UniqueConstraint("tenant_id", "email", name="uq_tenant_users_email"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantUserRoleModel(TenantBase):
    __tablename__ = "tenant_user_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "role", name="uq_tenant_user_roles_role"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("tenant_users.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantChannelModel(TenantBase):
    __tablename__ = "tenant_channels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_type", "external_identifier", name="uq_tenant_channel_identifier"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    channel_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    external_identifier: Mapped[str | None] = mapped_column(String(255), index=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantAIConfigModel(TenantBase):
    __tablename__ = "tenant_ai_configs"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_ai_configs_tenant"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="deepseek")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="deepseek-v4-flash")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    top_p: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    thinking_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantAgentPolicyModel(TenantBase):
    __tablename__ = "tenant_agent_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_agent_policies_tenant"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    require_write_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_message_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=4000)
    memory_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    session_ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    pending_action_ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    max_ui_options: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    allowed_intents: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantIntegrationModel(TenantBase):
    __tablename__ = "tenant_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "integration_type", "base_url", name="uq_tenant_integration_target"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    integration_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="ACTIVE")
    base_url: Mapped[str | None] = mapped_column(String(500))
    transport: Mapped[str | None] = mapped_column(String(80))
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantRateLimitModel(TenantBase):
    __tablename__ = "tenant_rate_limits"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_rate_limits_tenant"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    max_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    debounce_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    worker_retry_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    worker_lock_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantSecretModel(TenantBase):
    __tablename__ = "tenant_secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "secret_name", name="uq_tenant_secrets_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    secret_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_version: Mapped[str] = mapped_column(String(40), nullable=False)
    last_rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantFeatureFlagModel(TenantBase):
    __tablename__ = "tenant_feature_flags"
    __table_args__ = (UniqueConstraint("tenant_id", "feature_name", name="uq_tenant_feature_flags_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    feature_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantConfigurationVersionModel(TenantBase):
    __tablename__ = "tenant_configuration_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "version", name="uq_tenant_configuration_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    author_user_id: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    diff_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ControlPlaneRepository:
    def __init__(self, settings: Settings, encryption: SecretEncryptionService):
        self.settings = settings
        self.encryption = encryption
        connect_args: dict[str, Any] = {}
        if settings.resolved_database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(
            settings.resolved_database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        TenantBase.metadata.create_all(self.engine)
        self.ensure_default_tenant()

    def ensure_default_tenant(self) -> dict[str, Any]:
        default_id = self.settings.agent_default_tenant_id or "default"
        with self.SessionLocal() as session:
            record = session.get(TenantModel, default_id)
            if not record:
                now = utcnow()
                record = TenantModel(
                    id=default_id,
                    slug="default",
                    name="Default Tenant",
                    status="ACTIVE",
                    timezone="America/Sao_Paulo",
                    locale="pt-BR",
                    environment=self.settings.app_env,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return self._tenant_to_dict(record)

    def create_tenant(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        record = TenantModel(
            id=data.get("id") or str(uuid4()),
            slug=data["slug"],
            name=data["name"],
            legal_name=data.get("legal_name"),
            document=data.get("document"),
            status=data.get("status") or "ONBOARDING",
            timezone=data.get("timezone") or "America/Sao_Paulo",
            locale=data.get("locale") or "pt-BR",
            environment=data.get("environment") or self.settings.app_env,
            created_at=now,
            updated_at=now,
        )
        with self.SessionLocal() as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise TenantConflictError("Tenant slug or id already exists") from exc
            session.refresh(record)
            return self._tenant_to_dict(record)

    def list_tenants(self) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            records = session.scalars(select(TenantModel).order_by(TenantModel.created_at.desc())).all()
            return [self._tenant_to_dict(record) for record in records]

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = self._get_tenant_record(session, tenant_id)
            return self._tenant_to_dict(record) if record else None

    def update_tenant(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self.SessionLocal() as session:
            record = self._require_tenant_record(session, tenant_id)
            for key in [
                "slug",
                "name",
                "legal_name",
                "document",
                "status",
                "timezone",
                "locale",
                "environment",
            ]:
                if key in data:
                    setattr(record, key, data[key])
            record.updated_at = utcnow()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise TenantConflictError("Tenant slug or id already exists") from exc
            session.refresh(record)
            return self._tenant_to_dict(record)

    def get_configuration(self, tenant_id: str) -> dict[str, Any]:
        with self.SessionLocal() as session:
            tenant = self._require_tenant_record(session, tenant_id)
            active_version = self._active_version(session, tenant.id)
            return self._configuration_snapshot(session, tenant, active_version)

    def publish_configuration(
        self,
        *,
        tenant_id: str,
        author_user_id: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        with self.SessionLocal() as session:
            tenant = self._require_tenant_record(session, tenant_id)
            previous = self._active_version(session, tenant.id)
            snapshot = self._configuration_snapshot(session, tenant, previous)
            next_version = (session.scalar(select(func.max(TenantConfigurationVersionModel.version)).where(
                TenantConfigurationVersionModel.tenant_id == tenant.id
            )) or 0) + 1
            if previous:
                previous.status = "ARCHIVED"
            record = TenantConfigurationVersionModel(
                id=str(uuid4()),
                tenant_id=tenant.id,
                version=next_version,
                status="PUBLISHED",
                author_user_id=author_user_id,
                reason=reason,
                diff_json=self._build_diff(previous.snapshot_json if previous else {}, snapshot),
                snapshot_json=snapshot,
                created_at=utcnow(),
                published_at=utcnow(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._version_to_dict(record)

    def list_versions(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            tenant = self._require_tenant_record(session, tenant_id)
            records = session.scalars(
                select(TenantConfigurationVersionModel)
                .where(TenantConfigurationVersionModel.tenant_id == tenant.id)
                .order_by(TenantConfigurationVersionModel.version.desc())
            ).all()
            return [self._version_to_dict(record) for record in records]

    def rollback_configuration(
        self,
        *,
        tenant_id: str,
        version: int,
        author_user_id: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        with self.SessionLocal() as session:
            tenant = self._require_tenant_record(session, tenant_id)
            target = session.scalar(
                select(TenantConfigurationVersionModel).where(
                    TenantConfigurationVersionModel.tenant_id == tenant.id,
                    TenantConfigurationVersionModel.version == version,
                )
            )
            if not target:
                raise TenantNotFoundError("Configuration version not found")
            self._apply_snapshot(session, tenant.id, target.snapshot_json)
            previous = self._active_version(session, tenant.id)
            if previous:
                previous.status = "ARCHIVED"
            next_version = (session.scalar(select(func.max(TenantConfigurationVersionModel.version)).where(
                TenantConfigurationVersionModel.tenant_id == tenant.id
            )) or 0) + 1
            record = TenantConfigurationVersionModel(
                id=str(uuid4()),
                tenant_id=tenant.id,
                version=next_version,
                status="PUBLISHED",
                author_user_id=author_user_id,
                reason=reason or f"Rollback to version {version}",
                diff_json={"rollback_from": previous.version if previous else None, "rollback_to": version},
                snapshot_json=target.snapshot_json,
                created_at=utcnow(),
                published_at=utcnow(),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._version_to_dict(record)

    def get_branding(self, tenant_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(select(TenantBrandingModel).where(TenantBrandingModel.tenant_id == tenant_id))
            return self._branding_to_dict(record) if record else None

    def upsert_branding(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_single(TenantBrandingModel, tenant_id, data, self._branding_to_dict)

    def get_ai_config(self, tenant_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(select(TenantAIConfigModel).where(TenantAIConfigModel.tenant_id == tenant_id))
            return self._ai_config_to_dict(record) if record else None

    def upsert_ai_config(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        current = self.get_ai_config(tenant_id)
        if current:
            data["version"] = int(current.get("version") or 1) + 1
        return self._upsert_single(TenantAIConfigModel, tenant_id, data, self._ai_config_to_dict)

    def get_policies(self, tenant_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(select(TenantAgentPolicyModel).where(TenantAgentPolicyModel.tenant_id == tenant_id))
            return self._policy_to_dict(record) if record else None

    def upsert_policies(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_single(TenantAgentPolicyModel, tenant_id, data, self._policy_to_dict)

    def get_rate_limits(self, tenant_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(select(TenantRateLimitModel).where(TenantRateLimitModel.tenant_id == tenant_id))
            return self._rate_limit_to_dict(record) if record else None

    def upsert_rate_limits(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_single(TenantRateLimitModel, tenant_id, data, self._rate_limit_to_dict)

    def list_channels(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            records = session.scalars(
                select(TenantChannelModel)
                .where(TenantChannelModel.tenant_id == tenant_id)
                .order_by(TenantChannelModel.created_at.desc())
            ).all()
            return [self._channel_to_dict(record) for record in records]

    def create_channel(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._create_child(TenantChannelModel, tenant_id, data, self._channel_to_dict)

    def update_channel(self, tenant_id: str, channel_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._update_child(TenantChannelModel, tenant_id, channel_id, data, self._channel_to_dict)

    def list_integrations(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            records = session.scalars(
                select(TenantIntegrationModel)
                .where(TenantIntegrationModel.tenant_id == tenant_id)
                .order_by(TenantIntegrationModel.created_at.desc())
            ).all()
            return [self._integration_to_dict(record) for record in records]

    def create_integration(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._create_child(TenantIntegrationModel, tenant_id, data, self._integration_to_dict)

    def update_integration(self, tenant_id: str, integration_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._update_child(TenantIntegrationModel, tenant_id, integration_id, data, self._integration_to_dict)

    def list_users(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            records = session.scalars(
                select(TenantUserModel)
                .where(TenantUserModel.tenant_id == tenant_id)
                .order_by(TenantUserModel.created_at.desc())
            ).all()
            return [self._user_to_dict(session, record) for record in records]

    def create_user(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        roles = list(data.pop("roles", []) or [])
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            now = utcnow()
            record = TenantUserModel(
                id=data.get("id") or str(uuid4()),
                tenant_id=tenant_id,
                external_user_id=data.get("external_user_id"),
                name=data["name"],
                email=data.get("email"),
                status=data.get("status") or "ACTIVE",
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            self._replace_user_roles(session, tenant_id, record.id, roles)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise TenantConflictError("Tenant user already exists") from exc
            session.refresh(record)
            return self._user_to_dict(session, record)

    def update_user(self, tenant_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        roles_marker = object()
        roles = data.pop("roles", roles_marker)
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(
                select(TenantUserModel).where(
                    TenantUserModel.tenant_id == tenant_id,
                    TenantUserModel.id == user_id,
                )
            )
            if not record:
                raise TenantNotFoundError("Tenant user not found")
            for key in ["external_user_id", "name", "email", "status"]:
                if key in data:
                    setattr(record, key, data[key])
            if roles is not roles_marker:
                self._replace_user_roles(session, tenant_id, record.id, list(roles or []))
            record.updated_at = utcnow()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise TenantConflictError("Tenant user already exists") from exc
            session.refresh(record)
            return self._user_to_dict(session, record)

    def upsert_secret(self, tenant_id: str, secret_name: str, value: str) -> dict[str, Any]:
        encrypted = self.encryption.encrypt(value)
        now = utcnow()
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(
                select(TenantSecretModel).where(
                    TenantSecretModel.tenant_id == tenant_id,
                    TenantSecretModel.secret_name == secret_name,
                )
            )
            if not record:
                record = TenantSecretModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    secret_name=secret_name,
                    encrypted_value=encrypted,
                    encryption_version=self.encryption.version,
                    last_rotated_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.encrypted_value = encrypted
                record.encryption_version = self.encryption.version
                record.last_rotated_at = now
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._secret_to_public_dict(record)

    def list_feature_flags(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            records = session.scalars(
                select(TenantFeatureFlagModel)
                .where(TenantFeatureFlagModel.tenant_id == tenant_id)
                .order_by(TenantFeatureFlagModel.feature_name)
            ).all()
            return [self._feature_flag_to_dict(record) for record in records]

    def upsert_feature_flag(self, tenant_id: str, feature_name: str, data: dict[str, Any]) -> dict[str, Any]:
        data = {**data, "feature_name": feature_name}
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(
                select(TenantFeatureFlagModel).where(
                    TenantFeatureFlagModel.tenant_id == tenant_id,
                    TenantFeatureFlagModel.feature_name == feature_name,
                )
            )
            now = utcnow()
            if not record:
                record = TenantFeatureFlagModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    feature_name=feature_name,
                    enabled=bool(data.get("enabled", False)),
                    settings_json=data.get("settings_json") or {},
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                if "enabled" in data:
                    record.enabled = bool(data["enabled"])
                if "settings_json" in data:
                    record.settings_json = data["settings_json"] or {}
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._feature_flag_to_dict(record)

    def _upsert_single(self, model: type[Any], tenant_id: str, data: dict[str, Any], serializer: Any) -> dict[str, Any]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(select(model).where(model.tenant_id == tenant_id))
            now = utcnow()
            if not record:
                record = model(id=str(uuid4()), tenant_id=tenant_id, created_at=now, updated_at=now)
                session.add(record)
            for key, value in data.items():
                if hasattr(model, key):
                    setattr(record, key, value)
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return serializer(record)

    def _create_child(self, model: type[Any], tenant_id: str, data: dict[str, Any], serializer: Any) -> dict[str, Any]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            now = utcnow()
            record = model(id=str(uuid4()), tenant_id=tenant_id, created_at=now, updated_at=now)
            for key, value in data.items():
                if hasattr(model, key):
                    setattr(record, key, value)
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise TenantConflictError("Tenant scoped record already exists") from exc
            session.refresh(record)
            return serializer(record)

    def _update_child(
        self,
        model: type[Any],
        tenant_id: str,
        record_id: str,
        data: dict[str, Any],
        serializer: Any,
    ) -> dict[str, Any]:
        with self.SessionLocal() as session:
            self._require_tenant_record(session, tenant_id)
            record = session.scalar(select(model).where(model.tenant_id == tenant_id, model.id == record_id))
            if not record:
                raise TenantNotFoundError("Tenant scoped record not found")
            for key, value in data.items():
                if hasattr(model, key):
                    setattr(record, key, value)
            record.updated_at = utcnow()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise TenantConflictError("Tenant scoped record already exists") from exc
            session.refresh(record)
            return serializer(record)

    def _replace_user_roles(
        self,
        session: Any,
        tenant_id: str,
        user_id: str,
        roles: list[str],
    ) -> None:
        session.query(TenantUserRoleModel).filter_by(tenant_id=tenant_id, user_id=user_id).delete()
        now = utcnow()
        for role in sorted({role for role in roles if role}):
            session.add(
                TenantUserRoleModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role=role,
                    created_at=now,
                )
            )

    def _apply_snapshot(self, session: Any, tenant_id: str, snapshot: dict[str, Any]) -> None:
        for key, method in [
            ("branding", self._apply_single_snapshot),
            ("ai_config", self._apply_single_snapshot),
            ("policies", self._apply_single_snapshot),
            ("rate_limits", self._apply_single_snapshot),
        ]:
            payload = snapshot.get(key)
            if isinstance(payload, dict):
                model = {
                    "branding": TenantBrandingModel,
                    "ai_config": TenantAIConfigModel,
                    "policies": TenantAgentPolicyModel,
                    "rate_limits": TenantRateLimitModel,
                }[key]
                method(session, model, tenant_id, payload)

    @staticmethod
    def _apply_single_snapshot(session: Any, model: type[Any], tenant_id: str, payload: dict[str, Any]) -> None:
        record = session.scalar(select(model).where(model.tenant_id == tenant_id))
        now = utcnow()
        if not record:
            record = model(id=str(uuid4()), tenant_id=tenant_id, created_at=now, updated_at=now)
            session.add(record)
        for key, value in payload.items():
            if key not in {"id", "tenant_id", "created_at", "updated_at"} and hasattr(model, key):
                setattr(record, key, value)
        record.updated_at = now

    def _configuration_snapshot(
        self,
        session: Any,
        tenant: TenantModel,
        active_version: TenantConfigurationVersionModel | None,
    ) -> dict[str, Any]:
        channels = session.scalars(select(TenantChannelModel).where(TenantChannelModel.tenant_id == tenant.id)).all()
        integrations = session.scalars(
            select(TenantIntegrationModel).where(TenantIntegrationModel.tenant_id == tenant.id)
        ).all()
        users = session.scalars(select(TenantUserModel).where(TenantUserModel.tenant_id == tenant.id)).all()
        flags = session.scalars(select(TenantFeatureFlagModel).where(TenantFeatureFlagModel.tenant_id == tenant.id)).all()
        secrets = session.scalars(select(TenantSecretModel).where(TenantSecretModel.tenant_id == tenant.id)).all()
        branding = session.scalar(select(TenantBrandingModel).where(TenantBrandingModel.tenant_id == tenant.id))
        ai_config = session.scalar(select(TenantAIConfigModel).where(TenantAIConfigModel.tenant_id == tenant.id))
        policies = session.scalar(select(TenantAgentPolicyModel).where(TenantAgentPolicyModel.tenant_id == tenant.id))
        rate_limits = session.scalar(select(TenantRateLimitModel).where(TenantRateLimitModel.tenant_id == tenant.id))
        return {
            "tenant": self._tenant_to_dict(tenant),
            "active_version": active_version.version if active_version else None,
            "branding": self._branding_to_dict(branding) if branding else None,
            "ai_config": self._ai_config_to_dict(ai_config) if ai_config else None,
            "policies": self._policy_to_dict(policies) if policies else None,
            "rate_limits": self._rate_limit_to_dict(rate_limits) if rate_limits else None,
            "channels": [self._channel_to_dict(record) for record in channels],
            "integrations": [self._integration_to_dict(record) for record in integrations],
            "users": [self._user_to_dict(session, record) for record in users],
            "feature_flags": [self._feature_flag_to_dict(record) for record in flags],
            "secrets": [self._secret_to_public_dict(record) for record in secrets],
        }

    @staticmethod
    def _build_diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        changed = sorted(key for key in set(previous) | set(current) if previous.get(key) != current.get(key))
        return {"changed": changed}

    def _active_version(self, session: Any, tenant_id: str) -> TenantConfigurationVersionModel | None:
        return session.scalar(
            select(TenantConfigurationVersionModel)
            .where(
                TenantConfigurationVersionModel.tenant_id == tenant_id,
                TenantConfigurationVersionModel.status == "PUBLISHED",
            )
            .order_by(TenantConfigurationVersionModel.version.desc())
        )

    def _require_tenant_record(self, session: Any, tenant_id: str) -> TenantModel:
        record = self._get_tenant_record(session, tenant_id)
        if not record:
            raise TenantNotFoundError("Tenant not found")
        return record

    @staticmethod
    def _get_tenant_record(session: Any, tenant_id: str) -> TenantModel | None:
        return session.scalar(
            select(TenantModel).where((TenantModel.id == tenant_id) | (TenantModel.slug == tenant_id))
        )

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def _secret_to_public_dict(self, record: TenantSecretModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "secret_name": record.secret_name,
            "configured": True,
            "masked": self.encryption.mask(record.encrypted_value),
            "encryption_version": record.encryption_version,
            "last_rotated_at": self._dt(record.last_rotated_at),
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _user_to_dict(self, session: Any, record: TenantUserModel) -> dict[str, Any]:
        roles = session.scalars(
            select(TenantUserRoleModel.role)
            .where(
                TenantUserRoleModel.tenant_id == record.tenant_id,
                TenantUserRoleModel.user_id == record.id,
            )
            .order_by(TenantUserRoleModel.role)
        ).all()
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "external_user_id": record.external_user_id,
            "name": record.name,
            "email": record.email,
            "status": record.status,
            "roles": list(roles),
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _tenant_to_dict(self, record: TenantModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "slug": record.slug,
            "name": record.name,
            "legal_name": record.legal_name,
            "document": record.document,
            "status": record.status,
            "timezone": record.timezone,
            "locale": record.locale,
            "environment": record.environment,
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _branding_to_dict(self, record: TenantBrandingModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "logo_url": record.logo_url,
            "favicon_url": record.favicon_url,
            "primary_color": record.primary_color,
            "secondary_color": record.secondary_color,
            "assistant_name": record.assistant_name,
            "assistant_tone": record.assistant_tone,
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _ai_config_to_dict(self, record: TenantAIConfigModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "provider": record.provider,
            "model": record.model,
            "temperature": record.temperature,
            "max_tokens": record.max_tokens,
            "top_p": record.top_p,
            "system_prompt": record.system_prompt,
            "confidence_threshold": record.confidence_threshold,
            "thinking_enabled": record.thinking_enabled,
            "status": record.status,
            "version": record.version,
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _policy_to_dict(self, record: TenantAgentPolicyModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "require_write_confirmation": record.require_write_confirmation,
            "max_message_chars": record.max_message_chars,
            "memory_retention_days": record.memory_retention_days,
            "session_ttl_minutes": record.session_ttl_minutes,
            "pending_action_ttl_minutes": record.pending_action_ttl_minutes,
            "max_ui_options": record.max_ui_options,
            "allowed_intents": record.allowed_intents or [],
            "allowed_tools": record.allowed_tools or [],
            "settings_json": record.settings_json or {},
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _rate_limit_to_dict(self, record: TenantRateLimitModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "max_messages": record.max_messages,
            "window_seconds": record.window_seconds,
            "debounce_seconds": record.debounce_seconds,
            "worker_retry_attempts": record.worker_retry_attempts,
            "worker_lock_seconds": record.worker_lock_seconds,
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _channel_to_dict(self, record: TenantChannelModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "channel_type": record.channel_type,
            "status": record.status,
            "external_account_id": record.external_account_id,
            "external_identifier": record.external_identifier,
            "settings_json": record.settings_json or {},
            "secret_reference": record.secret_reference,
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _integration_to_dict(self, record: TenantIntegrationModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "integration_type": record.integration_type,
            "status": record.status,
            "base_url": record.base_url,
            "transport": record.transport,
            "settings_json": record.settings_json or {},
            "secret_reference": record.secret_reference,
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _feature_flag_to_dict(self, record: TenantFeatureFlagModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "feature_name": record.feature_name,
            "enabled": record.enabled,
            "settings_json": record.settings_json or {},
            "created_at": self._dt(record.created_at),
            "updated_at": self._dt(record.updated_at),
        }

    def _version_to_dict(self, record: TenantConfigurationVersionModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "version": record.version,
            "status": record.status,
            "author_user_id": record.author_user_id,
            "reason": record.reason,
            "diff": record.diff_json or {},
            "snapshot": record.snapshot_json,
            "created_at": self._dt(record.created_at),
            "published_at": self._dt(record.published_at),
        }


class TenantConfigurationService:
    def __init__(self, repository: ControlPlaneRepository):
        self.repository = repository
        self._cache: dict[tuple[str, int | None], dict[str, Any]] = {}

    def get_active_configuration(self, tenant_id: str) -> dict[str, Any]:
        configuration = self.repository.get_configuration(tenant_id)
        cache_key = (tenant_id, configuration.get("active_version"))
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        self._cache[cache_key] = configuration
        return configuration

    def invalidate(self, tenant_id: str) -> None:
        for key in list(self._cache):
            if key[0] == tenant_id:
                del self._cache[key]

    def publish(self, *, tenant_id: str, author_user_id: str | None, reason: str | None) -> dict[str, Any]:
        version = self.repository.publish_configuration(
            tenant_id=tenant_id,
            author_user_id=author_user_id,
            reason=reason,
        )
        self.invalidate(tenant_id)
        return version

    def rollback(
        self,
        *,
        tenant_id: str,
        version: int,
        author_user_id: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        restored = self.repository.rollback_configuration(
            tenant_id=tenant_id,
            version=version,
            author_user_id=author_user_id,
            reason=reason,
        )
        self.invalidate(tenant_id)
        return restored

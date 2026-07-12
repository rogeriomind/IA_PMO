from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TenantStatus = Literal["ACTIVE", "SUSPENDED", "ONBOARDING", "INACTIVE"]
ChannelType = Literal["telegram", "whatsapp", "webchat", "email"]
IntegrationType = Literal["pmo_board", "mcp", "langfuse", "redis"]


class TenantCreateRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = None
    document: str | None = None
    status: TenantStatus = "ONBOARDING"
    timezone: str = "America/Sao_Paulo"
    locale: str = "pt-BR"
    environment: str = "production"


class TenantPatchRequest(BaseModel):
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = None
    document: str | None = None
    status: TenantStatus | None = None
    timezone: str | None = None
    locale: str | None = None
    environment: str | None = None


class TenantBrandingRequest(BaseModel):
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    assistant_name: str | None = None
    assistant_tone: str | None = None


class TenantAIConfigRequest(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.2
    max_tokens: int = 4096
    top_p: float = 1.0
    system_prompt: str | None = None
    confidence_threshold: float = 0.75
    thinking_enabled: bool = False
    status: str = "ACTIVE"


class TenantPolicyRequest(BaseModel):
    require_write_confirmation: bool = True
    max_message_chars: int = 4000
    memory_retention_days: int = 90
    session_ttl_minutes: int = 1440
    pending_action_ttl_minutes: int = 15
    max_ui_options: int = 12
    allowed_intents: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    settings_json: dict[str, Any] = Field(default_factory=dict)


class TenantRateLimitRequest(BaseModel):
    max_messages: int = 20
    window_seconds: int = 60
    debounce_seconds: int = 2
    worker_retry_attempts: int = 3
    worker_lock_seconds: int = 60


class TenantChannelCreateRequest(BaseModel):
    channel_type: ChannelType
    status: str = "ACTIVE"
    external_account_id: str | None = None
    external_identifier: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)
    secret_reference: str | None = None


class TenantChannelPatchRequest(BaseModel):
    channel_type: ChannelType | None = None
    status: str | None = None
    external_account_id: str | None = None
    external_identifier: str | None = None
    settings_json: dict[str, Any] | None = None
    secret_reference: str | None = None


class TenantIntegrationCreateRequest(BaseModel):
    integration_type: IntegrationType
    status: str = "ACTIVE"
    base_url: str | None = None
    transport: str | None = None
    settings_json: dict[str, Any] = Field(default_factory=dict)
    secret_reference: str | None = None


class TenantIntegrationPatchRequest(BaseModel):
    integration_type: IntegrationType | None = None
    status: str | None = None
    base_url: str | None = None
    transport: str | None = None
    settings_json: dict[str, Any] | None = None
    secret_reference: str | None = None


class TenantUserCreateRequest(BaseModel):
    external_user_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    email: str | None = None
    status: str = "ACTIVE"
    roles: list[str] = Field(default_factory=list)


class TenantUserPatchRequest(BaseModel):
    external_user_id: str | None = None
    name: str | None = None
    email: str | None = None
    status: str | None = None
    roles: list[str] | None = None


class TenantSecretRequest(BaseModel):
    value: str = Field(min_length=1)


class TenantFeatureFlagRequest(BaseModel):
    enabled: bool
    settings_json: dict[str, Any] = Field(default_factory=dict)


class TenantPublishRequest(BaseModel):
    reason: str | None = None


class TenantTestResponse(BaseModel):
    status: Literal["ok", "not_configured"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

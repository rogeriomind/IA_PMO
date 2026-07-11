from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../.env.txt"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    service_name: str = "pmo-ai-agent-api"

    ai_provider: Literal["deepseek", "openai"] | str = Field(default="deepseek", alias="AI_PROVIDER")

    deepseek_api_key: SecretStr | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5-nano", alias="OPENAI_MODEL")
    llm_validate_model_on_health: bool = Field(
        default=True,
        validation_alias=AliasChoices("LLM_VALIDATE_MODEL_ON_HEALTH", "OPENAI_VALIDATE_MODEL_ON_HEALTH"),
    )

    database_url: str = Field(default="", alias="DATABASE_URL")

    mcp_board_url: str = Field(default="", alias="MCP_BOARD_URL")
    mcp_board_transport: Literal["http", "streamable_http", "sse", "stdio"] | str = Field(
        default="http", alias="MCP_BOARD_TRANSPORT"
    )
    mcp_board_doc_path: str = Field(
        default="/opt/shared/mcp/board_pmo.md", alias="MCP_BOARD_DOC_PATH"
    )
    mcp_tool_map_json: str = Field(default="", alias="MCP_TOOL_MAP_JSON")
    mcp_timeout_seconds: float = Field(default=15.0, alias="MCP_TIMEOUT_SECONDS")
    mcp_read_retries: int = Field(default=2, alias="MCP_READ_RETRIES")

    agent_intent_confidence_threshold: float = Field(
        default=0.75, alias="AGENT_INTENT_CONFIDENCE_THRESHOLD"
    )
    agent_api_token: SecretStr | None = Field(default=None, alias="AGENT_API_TOKEN")
    agent_default_tenant_id: str = Field(default="default", alias="AGENT_DEFAULT_TENANT_ID")
    agent_default_user_id: str = Field(default="system", alias="AGENT_DEFAULT_USER_ID")
    agent_default_user_roles: str = Field(
        default="board.read,board.write,board.manage",
        alias="AGENT_DEFAULT_USER_ROLES",
    )
    agent_max_message_chars: int = Field(default=4000, alias="AGENT_MAX_MESSAGE_CHARS")
    agent_tool_result_max_chars: int = Field(default=12000, alias="AGENT_TOOL_RESULT_MAX_CHARS")
    agent_thread_lock_ttl_seconds: int = Field(default=60, alias="AGENT_THREAD_LOCK_TTL_SECONDS")

    langfuse_enabled: bool = Field(default=True, alias="LANGFUSE_ENABLED")
    langfuse_public_key: SecretStr | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: SecretStr | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="", alias="LANGFUSE_HOST")

    agent_api_port: int = Field(default=8010, alias="AGENT_API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("ai_provider")
    @classmethod
    def normalize_ai_provider(cls, value: str) -> str:
        normalized = (value or "deepseek").strip().lower()
        if normalized not in {"deepseek", "openai"}:
            return "deepseek"
        return normalized

    @field_validator("mcp_board_transport")
    @classmethod
    def normalize_transport(cls, value: str) -> str:
        normalized = (value or "http").strip().lower()
        if normalized in {"streamable-http", "streamable"}:
            return "streamable_http"
        if normalized not in {"http", "streamable_http", "sse", "stdio"}:
            return "http"
        return normalized

    @property
    def resolved_database_url(self) -> str:
        raw = (self.database_url or "").strip()
        if not raw:
            return "sqlite:///./pmo_agent.db"
        if raw.startswith("postgres://"):
            return "postgresql+psycopg://" + raw.removeprefix("postgres://")
        if raw.startswith("postgresql+asyncpg://"):
            return "postgresql+psycopg://" + raw.removeprefix("postgresql+asyncpg://")
        if raw.startswith("postgresql://"):
            return "postgresql+psycopg://" + raw.removeprefix("postgresql://")
        return raw

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_model.strip())

    @property
    def llm_provider(self) -> str:
        return self.ai_provider.strip().lower() or "deepseek"

    @property
    def llm_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model.strip()
        return self.deepseek_model.strip()

    @property
    def llm_api_key(self) -> SecretStr | None:
        if self.llm_provider == "openai":
            return self.openai_api_key
        return self.deepseek_api_key or self.openai_api_key

    @property
    def llm_base_url(self) -> str | None:
        if self.llm_provider == "openai":
            return None
        return self.deepseek_base_url.strip() or "https://api.deepseek.com"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    @property
    def langfuse_configured(self) -> bool:
        return bool(
            self.langfuse_enabled
            and self.langfuse_public_key
            and self.langfuse_secret_key
            and self.langfuse_host.strip()
        )

    @property
    def default_user_roles(self) -> list[str]:
        return [
            role.strip()
            for role in self.agent_default_user_roles.split(",")
            if role.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

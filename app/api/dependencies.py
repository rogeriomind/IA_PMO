from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    correlation_id: str
    tenant_id: str
    user_id: str
    user_roles: list[str]


async def get_request_context(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_user_roles: str | None = Header(default=None, alias="X-User-Roles"),
) -> RequestContext:
    settings: Settings = request.app.state.settings
    authenticated = _validate_agent_token(settings, authorization, required=settings.is_production)

    request_id = x_request_id or str(uuid4())
    correlation_id = x_correlation_id or request_id
    roles = _parse_roles(x_user_roles) if authenticated or not settings.is_production else []
    roles = roles or settings.default_user_roles
    return RequestContext(
        request_id=request_id,
        correlation_id=correlation_id,
        tenant_id=x_tenant_id or settings.agent_default_tenant_id,
        user_id=x_user_id or settings.agent_default_user_id,
        user_roles=roles,
    )


async def get_authenticated_request_context(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_user_roles: str | None = Header(default=None, alias="X-User-Roles"),
) -> RequestContext:
    settings: Settings = request.app.state.settings
    authenticated = _validate_agent_token(settings, authorization, required=True)
    request_id = x_request_id or str(uuid4())
    correlation_id = x_correlation_id or request_id
    roles = _parse_roles(x_user_roles) if authenticated else []
    return RequestContext(
        request_id=request_id,
        correlation_id=correlation_id,
        tenant_id=x_tenant_id or settings.agent_default_tenant_id,
        user_id=x_user_id or settings.agent_default_user_id,
        user_roles=roles or settings.default_user_roles,
    )


async def get_admin_request_context(
    context: RequestContext = Depends(get_authenticated_request_context),
) -> RequestContext:
    roles = set(context.user_roles or [])
    if not roles.intersection({"admin", "agent.admin"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return context


def _parse_roles(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [role.strip() for role in raw.split(",") if role.strip()]


def _validate_agent_token(settings: Settings, authorization: str | None, *, required: bool) -> bool:
    expected_token = settings.agent_api_token.get_secret_value() if settings.agent_api_token else None
    if not expected_token:
        if required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Agent API token is not configured",
            )
        return False
    expected_header = f"Bearer {expected_token}"
    if authorization != expected_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Agent API token",
        )
    return True

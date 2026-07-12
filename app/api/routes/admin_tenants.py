from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import RequestContext, get_admin_request_context
from app.api.schemas.admin_tenants import (
    TenantAIConfigRequest,
    TenantBrandingRequest,
    TenantChannelCreateRequest,
    TenantChannelPatchRequest,
    TenantFeatureFlagRequest,
    TenantIntegrationCreateRequest,
    TenantIntegrationPatchRequest,
    TenantPatchRequest,
    TenantPolicyRequest,
    TenantPublishRequest,
    TenantRateLimitRequest,
    TenantSecretRequest,
    TenantTestResponse,
    TenantCreateRequest,
    TenantUserCreateRequest,
    TenantUserPatchRequest,
)
from app.tenancy.control_plane import (
    ControlPlaneRepository,
    TenantConflictError,
    TenantConfigurationService,
    TenantNotFoundError,
)
from app.tenancy.security import SecretEncryptionError


router = APIRouter(prefix="/admin/v1/tenants", tags=["tenant-admin"])

PLATFORM_ADMIN_ROLES = {"admin", "platform.admin", "agent.admin"}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreateRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_platform_admin(context)
    return _run(lambda: _repo(request).create_tenant(payload.model_dump()))


@router.get("")
async def list_tenants(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    repository = _repo(request)
    if _is_platform_admin(context):
        return repository.list_tenants()
    tenant = repository.get_tenant(context.tenant_id)
    return [tenant] if tenant else []


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    tenant = _repo(request).get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    payload: TenantPatchRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).update_tenant(tenant_id, payload.model_dump(exclude_unset=True)))


@router.get("/{tenant_id}/configuration")
async def get_configuration(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _config_service(request).get_active_configuration(tenant_id))


@router.put("/{tenant_id}/configuration")
async def put_configuration(
    tenant_id: str,
    payload: dict[str, Any],
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    repository = _repo(request)
    if "branding" in payload and isinstance(payload["branding"], dict):
        repository.upsert_branding(tenant_id, payload["branding"])
    if "ai_config" in payload and isinstance(payload["ai_config"], dict):
        repository.upsert_ai_config(tenant_id, payload["ai_config"])
    if "policies" in payload and isinstance(payload["policies"], dict):
        repository.upsert_policies(tenant_id, payload["policies"])
    if "rate_limits" in payload and isinstance(payload["rate_limits"], dict):
        repository.upsert_rate_limits(tenant_id, payload["rate_limits"])
    for feature_name, value in (payload.get("feature_flags") or {}).items():
        if isinstance(value, dict):
            repository.upsert_feature_flag(tenant_id, feature_name, value)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: repository.get_configuration(tenant_id))


@router.get("/{tenant_id}/branding")
async def get_branding(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).get_branding(tenant_id) or {})


@router.put("/{tenant_id}/branding")
async def put_branding(
    tenant_id: str,
    payload: TenantBrandingRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_branding(tenant_id, payload.model_dump()))


@router.get("/{tenant_id}/channels")
async def list_channels(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).list_channels(tenant_id))


@router.post("/{tenant_id}/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    tenant_id: str,
    payload: TenantChannelCreateRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).create_channel(tenant_id, payload.model_dump()))


@router.patch("/{tenant_id}/channels/{channel_id}")
async def update_channel(
    tenant_id: str,
    channel_id: str,
    payload: TenantChannelPatchRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).update_channel(tenant_id, channel_id, payload.model_dump(exclude_unset=True)))


@router.post("/{tenant_id}/channels/{channel_id}/test", response_model=TenantTestResponse)
async def test_channel(
    tenant_id: str,
    channel_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> TenantTestResponse:
    _require_tenant_access(context, tenant_id)
    channels = _repo(request).list_channels(tenant_id)
    channel = next((item for item in channels if item["id"] == channel_id), None)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    configured = channel.get("status") == "ACTIVE" and bool(channel.get("external_identifier"))
    return TenantTestResponse(
        status="ok" if configured else "not_configured",
        message="Channel configuration is present" if configured else "Channel is missing an external identifier",
        details={"channel_type": channel.get("channel_type")},
    )


@router.get("/{tenant_id}/ai-config")
async def get_ai_config(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).get_ai_config(tenant_id) or {})


@router.put("/{tenant_id}/ai-config")
async def put_ai_config(
    tenant_id: str,
    payload: TenantAIConfigRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_ai_config(tenant_id, payload.model_dump()))


@router.post("/{tenant_id}/ai-config/test", response_model=TenantTestResponse)
async def test_ai_config(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> TenantTestResponse:
    _require_tenant_access(context, tenant_id)
    ai_config = _repo(request).get_ai_config(tenant_id) or {}
    configured = bool(ai_config.get("provider") and ai_config.get("model"))
    return TenantTestResponse(
        status="ok" if configured else "not_configured",
        message="AI configuration is present" if configured else "AI provider/model are missing",
        details={"provider": ai_config.get("provider"), "model": ai_config.get("model")},
    )


@router.get("/{tenant_id}/integrations")
async def list_integrations(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).list_integrations(tenant_id))


@router.post("/{tenant_id}/integrations", status_code=status.HTTP_201_CREATED)
async def create_integration(
    tenant_id: str,
    payload: TenantIntegrationCreateRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).create_integration(tenant_id, payload.model_dump()))


@router.patch("/{tenant_id}/integrations/{integration_id}")
async def update_integration(
    tenant_id: str,
    integration_id: str,
    payload: TenantIntegrationPatchRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(
        lambda: _repo(request).update_integration(tenant_id, integration_id, payload.model_dump(exclude_unset=True))
    )


@router.post("/{tenant_id}/integrations/{integration_id}/test", response_model=TenantTestResponse)
async def test_integration(
    tenant_id: str,
    integration_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> TenantTestResponse:
    _require_tenant_access(context, tenant_id)
    integrations = _repo(request).list_integrations(tenant_id)
    integration = next((item for item in integrations if item["id"] == integration_id), None)
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    configured = integration.get("status") == "ACTIVE" and bool(integration.get("base_url") or integration.get("transport"))
    return TenantTestResponse(
        status="ok" if configured else "not_configured",
        message="Integration configuration is present" if configured else "Integration target is missing",
        details={"integration_type": integration.get("integration_type")},
    )


@router.get("/{tenant_id}/users")
async def list_users(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).list_users(tenant_id))


@router.post("/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    tenant_id: str,
    payload: TenantUserCreateRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).create_user(tenant_id, payload.model_dump()))


@router.patch("/{tenant_id}/users/{user_id}")
async def update_user(
    tenant_id: str,
    user_id: str,
    payload: TenantUserPatchRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).update_user(tenant_id, user_id, payload.model_dump(exclude_unset=True)))


@router.get("/{tenant_id}/policies")
async def get_policies(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).get_policies(tenant_id) or {})


@router.put("/{tenant_id}/policies")
async def put_policies(
    tenant_id: str,
    payload: TenantPolicyRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_policies(tenant_id, payload.model_dump()))


@router.get("/{tenant_id}/rate-limits")
async def get_rate_limits(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).get_rate_limits(tenant_id) or {})


@router.put("/{tenant_id}/rate-limits")
async def put_rate_limits(
    tenant_id: str,
    payload: TenantRateLimitRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_rate_limits(tenant_id, payload.model_dump()))


@router.post("/{tenant_id}/secrets/{secret_name}")
async def upsert_secret(
    tenant_id: str,
    secret_name: str,
    payload: TenantSecretRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_secret_admin(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_secret(tenant_id, secret_name, payload.value))


@router.post("/{tenant_id}/secrets/{secret_name}/rotate")
async def rotate_secret(
    tenant_id: str,
    secret_name: str,
    payload: TenantSecretRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_secret_admin(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_secret(tenant_id, secret_name, payload.value))


@router.get("/{tenant_id}/feature-flags")
async def list_feature_flags(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).list_feature_flags(tenant_id))


@router.put("/{tenant_id}/feature-flags/{feature_name}")
async def put_feature_flag(
    tenant_id: str,
    feature_name: str,
    payload: TenantFeatureFlagRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    _config_service(request).invalidate(tenant_id)
    return _run(lambda: _repo(request).upsert_feature_flag(tenant_id, feature_name, payload.model_dump()))


@router.post("/{tenant_id}/publish")
async def publish_configuration(
    tenant_id: str,
    payload: TenantPublishRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(
        lambda: _config_service(request).publish(
            tenant_id=tenant_id,
            author_user_id=context.user_id,
            reason=payload.reason,
        )
    )


@router.get("/{tenant_id}/versions")
async def list_versions(
    tenant_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    _require_tenant_access(context, tenant_id)
    return _run(lambda: _repo(request).list_versions(tenant_id))


@router.post("/{tenant_id}/versions/{version}/rollback")
async def rollback_configuration(
    tenant_id: str,
    version: int,
    payload: TenantPublishRequest,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    _require_tenant_access(context, tenant_id)
    return _run(
        lambda: _config_service(request).rollback(
            tenant_id=tenant_id,
            version=version,
            author_user_id=context.user_id,
            reason=payload.reason,
        )
    )


def _repo(request: Request) -> ControlPlaneRepository:
    return request.app.state.control_plane


def _config_service(request: Request) -> TenantConfigurationService:
    return request.app.state.tenant_config_service


def _is_platform_admin(context: RequestContext) -> bool:
    return bool(set(context.user_roles).intersection(PLATFORM_ADMIN_ROLES))


def _require_platform_admin(context: RequestContext) -> None:
    if not _is_platform_admin(context):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin role required")


def _require_tenant_access(context: RequestContext, tenant_id: str) -> None:
    if _is_platform_admin(context):
        return
    if "tenant.admin" in context.user_roles and context.tenant_id == tenant_id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role required")


def _require_secret_admin(context: RequestContext, tenant_id: str) -> None:
    _require_tenant_access(context, tenant_id)
    if "tenant.manager" in context.user_roles and not _is_platform_admin(context):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant manager cannot change secrets")


def _run(fn: Any) -> Any:
    try:
        return fn()
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TenantConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SecretEncryptionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

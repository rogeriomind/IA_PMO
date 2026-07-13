from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import RequestContext, get_admin_request_context
from app.storage.repository import (
    AgentEventModel,
    AgentThreadModel,
    PendingActionModel,
    PendingActionRepository,
    ToolExecutionAuditModel,
)
from app.tenancy import ControlPlaneRepository, TenantConfigurationService
from app.tenancy.control_plane import TenantNotFoundError


router = APIRouter(prefix="/admin/v1", tags=["admin-console"])


@router.get("/me")
async def me(context: RequestContext = Depends(get_admin_request_context)) -> dict[str, Any]:
    role = "Administrador" if _is_admin(context) else "Operador"
    return {
        "name": context.user_id or "IA PMO Admin",
        "role": role,
        "avatarUrl": "",
    }


@router.get("/dashboard")
async def dashboard(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    repository = _repository(request)
    tenant_id = context.tenant_id
    threads = _safe_query(repository, select(AgentThreadModel).where(AgentThreadModel.tenant_id == tenant_id))
    pending_actions = _pending_action_records(repository, tenant_id, limit=8)
    events = _event_records(repository, tenant_id, limit=50)
    audits = _audit_records(repository, tenant_id, limit=50)

    successful = sum(1 for audit in audits if audit.status.lower() in {"success", "completed", "ok"})
    avg_latency = int(sum(event.latency_ms for event in events) / len(events)) if events else 0
    pending_count = sum(1 for item in pending_actions if _action_status(item.status) == "Aguardando confirmação")
    by_day = _conversation_days(events)
    by_channel = Counter(_channel_label(thread.channel) for thread in threads)

    return {
        "kpis": [
            {
                "id": "conversations",
                "title": "Conversas",
                "value": str(len(threads)),
                "comparison": f"{sum(day['conversas'] for day in by_day)} eventos nos últimos 7 dias",
                "positive": True,
                "sparkline": [day["conversas"] for day in by_day],
            },
            {
                "id": "pending",
                "title": "Ações Pendentes",
                "value": str(pending_count),
                "comparison": f"{len(pending_actions)} ações recentes",
                "positive": pending_count <= len(pending_actions),
                "sparkline": [pending_count for _ in by_day],
            },
            {
                "id": "resolution",
                "title": "Taxa de Resolução",
                "value": _percent(successful, len(audits)),
                "comparison": f"{successful}/{len(audits)} execuções com sucesso",
                "positive": True,
                "sparkline": [successful for _ in by_day],
            },
            {
                "id": "response",
                "title": "Tempo Médio de Resposta",
                "value": _duration(avg_latency),
                "comparison": "Calculado pela auditoria de eventos",
                "positive": avg_latency <= 2000,
                "sparkline": [avg_latency for _ in by_day],
            },
        ],
        "conversationsByDay": by_day,
        "events": [_event_payload(event) for event in events[:8]],
        "pendingActions": [_pending_action_payload(action) for action in pending_actions],
        "platforms": _platform_metrics(by_channel),
    }


@router.get("/conversations")
async def conversations(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    repository = _repository(request)
    threads = _safe_query(
        repository,
        select(AgentThreadModel)
        .where(AgentThreadModel.tenant_id == context.tenant_id)
        .order_by(AgentThreadModel.updated_at.desc()),
    )
    pending = _pending_action_records(repository, context.tenant_id, limit=200)
    pending_by_thread = Counter(action.thread_id or action.conversation_id for action in pending)
    return [_conversation_payload(thread, pending_by_thread.get(thread.thread_id, 0), []) for thread in threads]


@router.get("/conversations/{thread_id}")
async def conversation_detail(
    thread_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    repository = _repository(request)
    with repository.SessionLocal() as session:
        thread = session.scalar(
            select(AgentThreadModel).where(
                AgentThreadModel.tenant_id == context.tenant_id,
                AgentThreadModel.thread_id == thread_id,
            )
        )
    if not thread:
        return _empty_conversation(thread_id, context.tenant_id)

    events = _safe_query(
        repository,
        select(AgentEventModel)
        .where(AgentEventModel.tenant_id == context.tenant_id, AgentEventModel.thread_id == thread_id)
        .order_by(AgentEventModel.created_at.asc()),
    )
    pending = _pending_action_records(repository, context.tenant_id, thread_id=thread_id, limit=50)
    return _conversation_payload(thread, len(pending), [_message_payload(event) for event in events])


@router.get("/pending-actions")
async def pending_actions(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    return [
        _pending_action_payload(action)
        for action in _pending_action_records(_repository(request), context.tenant_id, limit=100)
    ]


@router.get("/langgraph")
async def langgraph(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    return {
        "nodes": _langgraph_nodes(request),
        "executions": await langgraph_executions(request, context),
    }


@router.get("/langgraph/executions")
async def langgraph_executions(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    events = _event_records(_repository(request), context.tenant_id, limit=20)
    if not events:
        return []
    return [_execution_payload(event) for event in events]


@router.post("/langgraph/test")
async def langgraph_test(
    payload: dict[str, Any],
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    settings = request.app.state.settings
    mcp_client = request.app.state.mcp_client
    path = [
        "start",
        "tenant_context",
        "memory",
        "classify",
        "intent",
        "board_search",
        "format_response",
        "audit",
        "end",
    ]
    return {
        "id": f"test-{int(datetime.now(timezone.utc).timestamp())}",
        "label": "Teste manual de fluxo",
        "status": "Sucesso" if settings.llm_configured else "Falha",
        "path": path,
        "intent": "teste_conectividade",
        "confidence": 1 if settings.llm_configured else 0,
        "nodesExecuted": len(path),
        "mcp": f"mcp_tool_count={len(mcp_client.registry.semantic_map)}",
        "response": "Fluxo validado sem escrita real.",
        "tokens": 0,
        "cost": "US$ 0.0000",
        "durationMs": 0,
        "errors": [] if settings.llm_configured else ["LLM não configurado"],
        "input": _sanitize_dict(payload),
    }


@router.get("/integrations")
async def integrations(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    settings = request.app.state.settings
    mcp_client = request.app.state.mcp_client
    tracer = request.app.state.tracer
    rows = _configuration(request, context.tenant_id).get("integrations") or []
    configured = {row.get("integration_type"): row for row in rows}
    return [
        _integration_payload("pmo-board", "PMO Board", "pmo_board" in configured or mcp_client.mcp_loaded, "board via MCP"),
        _integration_payload("mcp", "MCP", mcp_client.mcp_loaded, f"{len(mcp_client.registry.semantic_map)} ferramentas"),
        _integration_payload("langfuse", "Langfuse", bool(tracer.enabled), "observabilidade"),
        _integration_payload("redis", "Redis", bool(settings.redis_enabled), "locks distribuídos"),
        _integration_payload("postgres", "PostgreSQL", True, "banco configurado"),
    ]


@router.post("/integrations/{integration_id}/test")
async def test_integration(
    integration_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    rows = await integrations(request, context)
    row = next((item for item in rows if item["id"] == integration_id), None)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return {"id": integration_id, "ok": row["status"] == "Conectado"}


@router.get("/configuration")
async def configuration(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    return _frontend_configuration(request, context.tenant_id)


@router.put("/configuration")
async def save_configuration(
    payload: dict[str, Any],
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    repository = _control_plane(request)
    tenant_id = context.tenant_id
    company = payload.get("company") or {}
    if company:
        update = {
            "name": company.get("name"),
            "legal_name": company.get("legalName"),
            "document": company.get("document"),
            "slug": company.get("slug"),
            "status": _tenant_status_to_backend(company.get("status")),
            "locale": company.get("language"),
            "timezone": company.get("timezone"),
            "environment": company.get("environment"),
        }
        repository.update_tenant(tenant_id, {key: value for key, value in update.items() if value is not None})

    identity = payload.get("identity") or {}
    if identity:
        repository.upsert_branding(
            tenant_id,
            {
                "primary_color": identity.get("primaryColor"),
                "secondary_color": identity.get("secondaryColor"),
                "assistant_name": identity.get("assistantName"),
                "assistant_tone": identity.get("tone"),
            },
        )

    model = payload.get("model") or {}
    if model or payload.get("systemPrompt"):
        repository.upsert_ai_config(
            tenant_id,
            {
                "provider": str(model.get("provider") or "OpenAI").lower(),
                "model": model.get("model") or "gpt-5-mini",
                "temperature": model.get("temperature", 0.2),
                "top_p": model.get("topP", 0.9),
                "max_tokens": model.get("maxTokens", 2400),
                "thinking_enabled": bool(model.get("thinkingEnabled", False)),
                "confidence_threshold": model.get("confidenceThreshold", 0.72),
                "system_prompt": payload.get("systemPrompt"),
                "status": "ACTIVE",
            },
        )
    _config_service(request).invalidate(tenant_id)
    return _frontend_configuration(request, tenant_id)


@router.post("/configuration/publish")
async def publish_configuration(
    payload: dict[str, Any],
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> dict[str, Any]:
    reason = payload.get("reason") or payload.get("justification") or "Publicação via admin-web"
    return _config_service(request).publish(
        tenant_id=context.tenant_id,
        author_user_id=context.user_id,
        reason=reason,
    )


@router.get("/audit")
async def audit(
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> list[dict[str, Any]]:
    audits = _audit_records(_repository(request), context.tenant_id, limit=50)
    if audits:
        return [
            {
                "id": audit.id,
                "event": f"{audit.tool_name} - {audit.status}",
                "actor": audit.user_id,
                "createdAt": _format_dt(audit.created_at),
            }
            for audit in audits
        ]
    return [
        {
            "id": event.id,
            "event": f"{event.message_type} - {event.status}",
            "actor": event.user_id,
            "createdAt": _format_dt(event.created_at),
        }
        for event in _event_records(_repository(request), context.tenant_id, limit=50)
    ]


def _repository(request: Request) -> PendingActionRepository:
    return request.app.state.repository


def _control_plane(request: Request) -> ControlPlaneRepository:
    return request.app.state.control_plane


def _config_service(request: Request) -> TenantConfigurationService:
    return request.app.state.tenant_config_service


def _configuration(request: Request, tenant_id: str) -> dict[str, Any]:
    try:
        return _config_service(request).get_active_configuration(tenant_id)
    except TenantNotFoundError:
        _control_plane(request).ensure_default_tenant()
        return _config_service(request).get_active_configuration(tenant_id)


def _safe_query(repository: PendingActionRepository, statement: Any) -> list[Any]:
    try:
        with repository.SessionLocal() as session:
            return list(session.scalars(statement).all())
    except SQLAlchemyError:
        return []


def _pending_action_records(
    repository: PendingActionRepository,
    tenant_id: str,
    *,
    thread_id: str | None = None,
    limit: int,
) -> list[PendingActionModel]:
    statement = select(PendingActionModel).where(PendingActionModel.tenant_id == tenant_id)
    if thread_id:
        statement = statement.where(PendingActionModel.thread_id == thread_id)
    return _safe_query(repository, statement.order_by(PendingActionModel.created_at.desc()).limit(limit))


def _event_records(repository: PendingActionRepository, tenant_id: str, *, limit: int) -> list[AgentEventModel]:
    return _safe_query(
        repository,
        select(AgentEventModel)
        .where(AgentEventModel.tenant_id == tenant_id)
        .order_by(AgentEventModel.created_at.desc())
        .limit(limit),
    )


def _audit_records(repository: PendingActionRepository, tenant_id: str, *, limit: int) -> list[ToolExecutionAuditModel]:
    return _safe_query(
        repository,
        select(ToolExecutionAuditModel)
        .where(ToolExecutionAuditModel.tenant_id == tenant_id)
        .order_by(ToolExecutionAuditModel.created_at.desc())
        .limit(limit),
    )


def _conversation_payload(
    thread: AgentThreadModel,
    pending_actions: int,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = thread.state_summary or {}
    last_message = summary.get("last_message") or summary.get("message") or "Sem mensagem textual recente"
    return {
        "threadId": thread.thread_id,
        "tenantId": thread.tenant_id,
        "title": summary.get("title") or thread.user_name or thread.thread_id,
        "channel": _channel_label(thread.channel),
        "status": "Pendente" if pending_actions else "Ativa",
        "user": thread.user_name or thread.user_id,
        "project": summary.get("project") or summary.get("project_id") or "PMO Board",
        "startedAt": _format_dt(thread.created_at),
        "lastActivity": _format_dt(thread.updated_at),
        "tags": [thread.current_flow, thread.current_step],
        "pendingActions": pending_actions,
        "estimatedCost": "US$ 0.0000",
        "tokens": 0,
        "isMine": True,
        "unreadCount": 0,
        "lastMessage": str(last_message),
        "messages": messages,
    }


def _empty_conversation(thread_id: str, tenant_id: str) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "tenantId": tenant_id,
        "title": thread_id,
        "channel": "Web Chat",
        "status": "Encerrada",
        "user": "Desconhecido",
        "project": "PMO Board",
        "startedAt": "",
        "lastActivity": "",
        "tags": [],
        "pendingActions": 0,
        "estimatedCost": "US$ 0.0000",
        "tokens": 0,
        "isMine": False,
        "unreadCount": 0,
        "lastMessage": "",
        "messages": [],
    }


def _message_payload(event: AgentEventModel) -> dict[str, Any]:
    output = event.output_payload_sanitized or {}
    body = output.get("message") or output.get("response") or event.message_type
    return {
        "id": event.event_id,
        "author": "agent" if event.message_type in {"agent_response", "tool_result"} else "user",
        "body": str(body),
        "createdAt": _format_dt(event.created_at),
        "deliveryStatus": "entregue",
    }


def _pending_action_payload(action: PendingActionModel) -> dict[str, Any]:
    preview = action.preview or {}
    payload = action.payload or {}
    return {
        "id": action.id,
        "description": str(preview.get("title") or payload.get("title") or action.tool_name or action.action_type),
        "thread": action.thread_id or action.conversation_id,
        "createdAt": _format_dt(action.created_at),
        "priority": _priority(payload.get("priority") or preview.get("priority")),
        "status": _action_status(action.status),
    }


def _event_payload(event: AgentEventModel) -> dict[str, Any]:
    return {
        "id": event.event_id,
        "kind": "error" if event.status.lower() in {"error", "failed"} else "conversation",
        "title": event.message_type,
        "description": event.step or event.flow or "Evento registrado pelo agente",
        "occurredAt": _relative(event.created_at),
    }


def _execution_payload(event: AgentEventModel) -> dict[str, Any]:
    failed = event.status.lower() in {"error", "failed"}
    path = ["start", "tenant_context", "memory", "classify", "intent"]
    if event.flow == "task_create":
        path += ["extract_entities", "validate_fields", "resolve_owner", "prepare_action", "confirm"]
    elif event.flow == "task_update":
        path += ["search_task", "select_task", "extract_changes", "prepare_action", "confirm"]
    else:
        path += ["board_search", "format_response"]
    path += ["error" if failed else "audit", "end"]
    return {
        "id": event.event_id,
        "label": f"{event.message_type} - {_format_dt(event.created_at)}",
        "status": "Falha" if failed else "Sucesso",
        "path": path,
        "intent": event.flow or event.message_type,
        "confidence": 1,
        "nodesExecuted": len(path),
        "mcp": "board_search_tasks",
        "response": event.status,
        "tokens": 0,
        "cost": "US$ 0.0000",
        "durationMs": event.latency_ms,
        "errors": [event.status] if failed else [],
    }


def _frontend_configuration(request: Request, tenant_id: str) -> dict[str, Any]:
    raw = _configuration(request, tenant_id)
    tenant = raw.get("tenant") or {}
    branding = raw.get("branding") or {}
    ai_config = raw.get("ai_config") or {}
    policies = raw.get("policies") or {}
    rate_limits = raw.get("rate_limits") or {}
    return {
        "company": {
            "name": tenant.get("name") or "IA PMO",
            "legalName": tenant.get("legal_name") or "",
            "document": tenant.get("document") or "",
            "slug": tenant.get("slug") or tenant_id,
            "status": _tenant_status_to_frontend(tenant.get("status")),
            "language": tenant.get("locale") or "pt-BR",
            "timezone": tenant.get("timezone") or "America/Sao_Paulo",
            "environment": tenant.get("environment") or "production",
        },
        "identity": {
            "primaryColor": branding.get("primary_color") or "#6D3DF5",
            "secondaryColor": branding.get("secondary_color") or "#F2EDFF",
            "assistantName": branding.get("assistant_name") or "IA PMO",
            "tone": branding.get("assistant_tone") or "Objetivo, cordial e orientado a ação",
            "welcomeMessage": "Olá, posso ajudar com status, tarefas, bloqueios e relatórios do seu PMO.",
        },
        "model": {
            "provider": "OpenAI" if (ai_config.get("provider") or "").lower() == "openai" else "DeepSeek",
            "model": ai_config.get("model") or request.app.state.settings.llm_model or "gpt-5-mini",
            "temperature": ai_config.get("temperature", 0.2),
            "topP": ai_config.get("top_p", 0.9),
            "maxTokens": ai_config.get("max_tokens", 2400),
            "thinkingEnabled": bool(ai_config.get("thinking_enabled", False)),
            "confidenceThreshold": ai_config.get("confidence_threshold", 0.72),
        },
        "systemPrompt": ai_config.get("system_prompt") or "",
        "policies": {
            "requireConfirmation": policies.get("require_write_confirmation", True),
            "allowCreate": True,
            "allowUpdate": True,
            "allowMove": True,
            "allowComments": True,
            "maxActions": 5,
            "confirmationExpiration": policies.get("pending_action_ttl_minutes", 15),
            "memoryRetention": policies.get("memory_retention_days", 90),
            "optionLimit": policies.get("max_ui_options", 12),
            "allowedIntents": policies.get("allowed_intents") or [],
        },
        "tools": _tool_policies(),
        "channels": _channel_configs(raw.get("channels") or []),
        "integrations": [],
        "observability": {
            "langfuseEnabled": bool(request.app.state.tracer.enabled),
            "samplingRate": 1,
            "logPrompts": True,
            "logResponses": True,
            "logCost": True,
            "retentionDays": 180,
            "dataMasking": True,
        },
        "parameters": {
            "debounce": rate_limits.get("debounce_seconds", 2),
            "rateLimit": rate_limits.get("max_messages", 20),
            "rateLimitWindow": rate_limits.get("window_seconds", 60),
            "retries": rate_limits.get("worker_retry_attempts", 3),
            "queueLock": rate_limits.get("worker_lock_seconds", 60),
            "workerSleep": 5,
            "sessionTtl": policies.get("session_ttl_minutes", 1440),
            "pendingActionTtl": policies.get("pending_action_ttl_minutes", 15),
            "selectionTtl": 30,
        },
        "security": {
            "roles": ["Administrador", "Operador", "Leitor"],
            "internalTokens": ["AGENT_API_TOKEN=****"],
            "secrets": [f"{secret.get('secret_name')}={secret.get('masked', '****')}" for secret in raw.get("secrets") or []],
            "lastRotation": "",
            "activeSessions": 0,
            "ipAllowlist": [],
            "auditEnabled": True,
        },
    }


def _tool_policies() -> list[dict[str, Any]]:
    names = [
        "board_search_tasks",
        "board_get_task",
        "board_create_task",
        "board_update_task",
        "board_move_task",
        "board_add_comment",
        "board_get_project_status",
        "board_list_blockers",
        "board_list_my_tasks",
    ]
    return [
        {
            "name": name,
            "enabled": True,
            "type": "write" if any(token in name for token in ["create", "update", "move", "comment"]) else "read",
            "requiresConfirmation": any(token in name for token in ["create", "update", "move", "comment"]),
            "roles": ["Administrador", "Operador"],
            "timeout": 15,
            "retries": 2,
        }
        for name in names
    ]


def _channel_configs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {str(row.get("channel_type", "")).lower(): row for row in rows}
    return [
        _channel_config("Telegram", by_name.get("telegram")),
        _channel_config("WhatsApp", by_name.get("whatsapp")),
        _channel_config("Web Chat", by_name.get("webchat")),
        _channel_config("Email", by_name.get("email")),
    ]


def _channel_config(name: str, row: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "name": name,
        "status": _integration_status(row.get("status") if row else None),
        "tokenPreview": f"{name.lower().replace(' ', '_')}_****",
    }


def _integration_payload(id_: str, name: str, ok: bool, latency: str) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "status": "Conectado" if ok else "Em configuração",
        "lastCheck": _format_dt(datetime.now(timezone.utc)),
        "latency": latency,
        "recentError": None if ok else "Integração ainda não configurada.",
    }


def _langgraph_nodes(request: Request) -> dict[str, dict[str, Any]]:
    def base(label: str, node_type: str, description: str) -> dict[str, Any]:
        return {
            "label": label,
            "nodeType": node_type,
            "description": description,
            "model": request.app.state.settings.llm_model if node_type == "llm" else None,
            "prompt": "Prompt operacional versionado" if node_type == "llm" else None,
            "temperature": 0.2 if node_type == "llm" else None,
            "maxTokens": 2400 if node_type == "llm" else None,
            "tool": label if node_type == "mcp" else None,
            "timeout": "15s" if node_type == "mcp" else "8s",
            "retries": 2 if node_type == "mcp" else 1,
            "entryConditions": ["Tenant ativo", "Usuário autenticado"],
            "nextRoutes": [],
            "lastRuns": [],
            "successRate": "N/D",
            "averageTime": "N/D",
            "averageCost": "US$ 0.0000",
            "status": "Não executado",
        }

    return {
        "start": base("START", "start-end", "Início da execução."),
        "tenant_context": base("Carregar Contexto do Tenant", "context", "Carrega políticas e configuração."),
        "memory": base("Carregar Memória", "context", "Carrega histórico recente."),
        "classify": base("Classificar Intenção", "llm", "Classifica a mensagem."),
        "intent": base("Qual é a intenção?", "decision", "Escolhe rota de execução."),
        "extract_entities": base("Extrair Entidades", "llm", "Extrai campos da tarefa."),
        "validate_fields": base("Validar Campos", "llm", "Valida campos obrigatórios."),
        "resolve_owner": base("Resolver Responsável", "mcp", "Resolve responsável no board."),
        "prepare_action": base("Preparar Ação", "llm", "Prepara ação auditável."),
        "confirm": base("Solicitar Confirmação", "human", "Aguarda confirmação humana."),
        "create_task": base("board_create_task", "mcp", "Cria tarefa no board."),
        "search_task": base("Buscar Tarefa", "mcp", "Busca tarefa candidata."),
        "select_task": base("Selecionar Tarefa", "llm", "Seleciona tarefa."),
        "extract_changes": base("Extrair Alterações", "llm", "Extrai alterações."),
        "update_task": base("board_update_task", "mcp", "Atualiza tarefa."),
        "validate_status": base("Validar Status", "llm", "Valida status destino."),
        "move_task": base("board_move_task", "mcp", "Move tarefa."),
        "board_search": base("board_search_tasks", "mcp", "Consulta tarefas."),
        "project_status": base("board_get_project_status", "mcp", "Consulta status do projeto."),
        "blockers": base("board_list_blockers", "mcp", "Lista bloqueios."),
        "my_tasks": base("board_list_my_tasks", "mcp", "Lista minhas tarefas."),
        "format_response": base("Formatar Resposta", "llm", "Formata resposta final."),
        "answer": base("Responder Dúvida", "llm", "Responde dúvidas gerais."),
        "audit": base("Registrar Evento", "audit", "Registra auditoria."),
        "end": base("END", "start-end", "Fim da execução."),
        "error": base("Fallback de Erro", "error", "Tratamento de erro."),
    }


def _conversation_days(events: list[AgentEventModel]) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date()
    counts = Counter(event.created_at.date() for event in events if event.created_at)
    return [
        {"day": (today - timedelta(days=offset)).strftime("%d/%m"), "conversas": counts[today - timedelta(days=offset)]}
        for offset in range(6, -1, -1)
    ]


def _platform_metrics(counter: Counter[str]) -> list[dict[str, Any]]:
    total = sum(counter.values())
    colors = {"WhatsApp": "#6D3DF5", "Telegram": "#2563EB", "Web Chat": "#16A34A", "Email": "#DC2626"}
    channels = ["WhatsApp", "Telegram", "Web Chat", "Email"]
    return [
        {
            "name": channel,
            "value": round((counter[channel] / total) * 100) if total else 0,
            "color": colors[channel],
        }
        for channel in channels
    ]


def _sanitize_dict(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {"token", "secret", "password", "api_key", "authorization"}
    return {
        key: "***" if any(block in key.lower() for block in blocked) else value
        for key, value in payload.items()
    }


def _format_dt(value: datetime | None) -> str:
    if not value:
        return ""
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")


def _relative(value: datetime | None) -> str:
    if not value:
        return ""
    minutes = max(1, round((datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() / 60))
    if minutes < 60:
        return f"há {minutes} min"
    hours = round(minutes / 60)
    if hours < 24:
        return f"há {hours} h"
    return _format_dt(value)


def _duration(milliseconds: int) -> str:
    if milliseconds <= 0:
        return "0s"
    seconds = round(milliseconds / 1000)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def _percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((part / total) * 100)}%"


def _priority(value: Any) -> str:
    normalized = str(value or "").upper()
    if normalized in {"HIGH", "ALTA"}:
        return "Alta"
    if normalized in {"LOW", "BAIXA"}:
        return "Baixa"
    return "Média"


def _action_status(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized in {"confirmed", "executed", "completed", "success"}:
        return "Confirmada"
    if normalized in {"cancelled", "canceled", "failed"}:
        return "Cancelada"
    return "Aguardando confirmação"


def _channel_label(value: Any) -> str:
    normalized = str(value or "").lower()
    if "whatsapp" in normalized:
        return "WhatsApp"
    if "telegram" in normalized:
        return "Telegram"
    if "email" in normalized:
        return "Email"
    return "Web Chat"


def _tenant_status_to_frontend(value: Any) -> str:
    return "suspended" if str(value or "").upper() == "SUSPENDED" else "active"


def _tenant_status_to_backend(value: Any) -> str:
    return "SUSPENDED" if str(value or "").lower() == "suspended" else "ACTIVE"


def _integration_status(value: Any) -> str:
    normalized = str(value or "").upper()
    if normalized == "ACTIVE":
        return "Conectado"
    if normalized in {"ERROR", "FAILED"}:
        return "Erro"
    if normalized in {"DISABLED", "INACTIVE"}:
        return "Desconectado"
    return "Em configuração"


def _is_admin(context: RequestContext) -> bool:
    return bool(set(context.user_roles).intersection({"admin", "platform.admin", "tenant.admin", "agent.admin"}))

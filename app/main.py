from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status

from app.agent.domains.projects.graph import build_project_subgraph
from app.agent.domains.projects.nodes import ProjectNodes
from app.agent.domains.tasks.graph import build_task_query_subgraph, build_task_write_subgraph
from app.agent.domains.tasks.nodes import TaskQueryNodes, TaskWriteNodes
from app.agent.extraction.extractor import TaskExtractionService
from app.agent.graph.builder import build_main_agent_graph
from app.agent.graph.nodes import MainGraphNodes
from app.agent.main_graph.builder import build_pmo_agent_graph
from app.agent.main_graph.nodes import PMOMainGraphNodes
from app.agent.mcp_gateway import BoardToolsExecutor, MCPGateway
from app.agent.observability import ObservabilityService
from app.agent.routing import HybridIntentRouter
from app.agent.service import AgentWorkflowService
from app.agent.subgraphs.confirmation.nodes import ConfirmationSubgraph
from app.agent.subgraphs.questions.nodes import QuestionsSubgraph
from app.agent.subgraphs.status.nodes import StatusSubgraph
from app.agent.subgraphs.task_create.nodes import CreateTaskSubgraph
from app.agent.subgraphs.task_update.nodes import UpdateTaskSubgraph
from app.agent.subgraphs.welcome.nodes import WelcomeMenuSubgraph
from app.agent.thread_lock import ThreadLockManager
from app.agent.tool_registry import ToolRegistry
from app.application.agent_service import AgentV2Service
from app.application.assignee_resolver import AssigneeResolver
from app.application.confirmation_service import AgentConfirmationService as AgentV2ConfirmationService
from app.application.draft_service import DraftService
from app.application.memory_service import MemoryService
from app.application.task_selection_service import TaskSelectionService
from app.api.middleware import install_correlation_middleware
from app.api.routes.admin_tenants import router as admin_tenants_router
from app.api.routes.agent_v1 import router as agent_v1_router
from app.api.routes.agent_v2 import router as agent_v2_router
from app.config import Settings, get_settings
from app.graph.builder import build_confirmation_graph, build_invoke_graph
from app.graph.nodes import AgentGraphNodes
from app.mcp.board_tools import BoardTools
from app.mcp.board_tools import normalize_priority, normalize_status
from app.mcp.client import MCPBoardClient
from app.infrastructure.observability.metrics import AgentMetrics
from app.infrastructure.redis.locks import RedisThreadLockManager
from app.observability.langfuse import LangfuseTracer
from app.schemas import (
    AgentAction,
    AgentConfirmRequest,
    AgentConfirmResponse,
    AgentInvokeRequest,
    AgentInvokeResponse,
    ExternalAgentProcessRequest,
    ExternalAgentProcessResponse,
    ExternalBoardAction,
    HealthResponse,
    Intent,
)
from app.services.confirmation_service import ConfirmationService
from app.services.intent_service import IntentService
from app.services.pending_action_service import PendingActionService
from app.services.response_service import ResponseService
from app.storage.repository import PendingActionRepository
from app.structured_logging import configure_logging
from app.tenancy import ControlPlaneRepository, SecretEncryptionService, TenantConfigurationService

logger = logging.getLogger(__name__)


LEGACY_INTENT_BY_INTENT = {
    Intent.TASK_CREATE: "create_task",
    Intent.TASK_UPDATE: "update_task",
    Intent.TASK_MOVE: "move_activity",
    Intent.TASK_COMMENT: "add_comment",
    Intent.STATUS_BOARD: "query_tasks",
    Intent.BOARD_QUESTION: "query_tasks",
    Intent.SMALLTALK: "unknown",
    Intent.UNKNOWN: "unknown",
}

LEGACY_ACTION_BY_INTENT = {
    Intent.TASK_CREATE: "create_activity",
    Intent.TASK_UPDATE: "update_activity",
    Intent.TASK_MOVE: "move_activity",
    Intent.TASK_COMMENT: "add_comment",
    Intent.STATUS_BOARD: "query_activities",
    Intent.BOARD_QUESTION: "query_activities",
    Intent.SMALLTALK: "unknown",
    Intent.UNKNOWN: "unknown",
}


def create_app(
    *,
    settings: Settings | None = None,
    board_tools_override: Any | None = None,
    repository_override: PendingActionRepository | None = None,
) -> FastAPI:
    settings_override = settings
    route_settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings = settings_override or route_settings
        configure_logging(app_settings.log_level)
        app_settings.validate_runtime_requirements()

        repository = repository_override or PendingActionRepository(app_settings)
        repository.init_db()
        encryption = SecretEncryptionService(
            app_settings.encryption_key.get_secret_value() if app_settings.encryption_key else None
        )
        control_plane = ControlPlaneRepository(app_settings, encryption)
        control_plane.init_db()

        mcp_client = MCPBoardClient(app_settings)
        board_tools = board_tools_override or BoardTools(mcp_client)
        gateway_board_tools = board_tools_override or BoardTools(mcp_client, read_retries=0)
        if board_tools_override is None:
            try:
                await mcp_client.startup()
            except Exception:
                logger.exception("Failed to start persistent MCP session pool; MCP calls will retry lazily")
        tracer = LangfuseTracer(app_settings)
        intent_service = IntentService(app_settings, tracer=tracer)
        response_service = ResponseService()
        pending_actions = PendingActionService(repository)
        confirmation_service = ConfirmationService(pending_actions, board_tools)
        nodes = AgentGraphNodes(
            intent_service=intent_service,
            pending_actions=pending_actions,
            response_service=response_service,
            board_tools=board_tools,
            confirmation_service=confirmation_service,
            tracer=tracer,
        )

        app.state.settings = app_settings
        app.state.repository = repository
        app.state.control_plane = control_plane
        app.state.tenant_config_service = TenantConfigurationService(control_plane)
        app.state.mcp_client = mcp_client
        app.state.board_tools = board_tools
        app.state.tracer = tracer
        app.state.intent_service = intent_service
        app.state.invoke_graph = build_invoke_graph(nodes)
        app.state.confirm_graph = build_confirmation_graph(nodes)

        tool_registry = ToolRegistry(
            read_timeout_seconds=app_settings.mcp_timeout_seconds,
            write_timeout_seconds=app_settings.mcp_timeout_seconds,
            read_retries=app_settings.mcp_read_retries,
        )
        gateway = MCPGateway(
            registry=tool_registry,
            executor=BoardToolsExecutor(gateway_board_tools),
            repository=repository,
            result_max_chars=app_settings.agent_tool_result_max_chars,
        )
        v1_router = HybridIntentRouter(app_settings, tracer=tracer)
        observability = ObservabilityService(tracer)
        task_query_subgraph = build_task_query_subgraph(TaskQueryNodes(gateway))
        task_write_subgraph = build_task_write_subgraph(TaskWriteNodes(gateway, repository))
        project_subgraph = build_project_subgraph(ProjectNodes(gateway))
        main_graph_nodes = MainGraphNodes(
            settings=app_settings,
            router=v1_router,
            repository=repository,
        )
        v1_graph = build_main_agent_graph(
            nodes=main_graph_nodes,
            task_query_subgraph=task_query_subgraph,
            task_write_subgraph=task_write_subgraph,
            project_subgraph=project_subgraph,
        )
        app.state.tool_registry = tool_registry
        app.state.mcp_gateway = gateway
        app.state.v1_agent_graph = v1_graph
        app.state.v1_agent_service = AgentWorkflowService(
            graph=v1_graph,
            gateway=gateway,
            repository=repository,
            observability=observability,
            thread_locks=ThreadLockManager(app_settings.agent_thread_lock_ttl_seconds),
        )
        memory_service = MemoryService(repository, app_settings)
        selection_service = TaskSelectionService(repository, app_settings)
        draft_service = DraftService(repository, app_settings)
        extraction_service = TaskExtractionService(app_settings, tracer=tracer)
        assignee_resolver = AssigneeResolver(board_tools=board_tools, repository=repository)
        v2_confirmation_service = AgentV2ConfirmationService(repository, gateway)
        welcome_subgraph = WelcomeMenuSubgraph()
        status_subgraph = StatusSubgraph(
            gateway=gateway,
            selections=selection_service,
            settings=app_settings,
            assignees=assignee_resolver,
        )
        create_subgraph = CreateTaskSubgraph(
            extractor=extraction_service,
            drafts=draft_service,
            assignees=assignee_resolver,
            repository=repository,
            settings=app_settings,
        )
        update_subgraph = UpdateTaskSubgraph(
            gateway=gateway,
            extractor=extraction_service,
            selections=selection_service,
            drafts=draft_service,
            assignees=assignee_resolver,
            repository=repository,
            settings=app_settings,
        )
        confirmation_subgraph = ConfirmationSubgraph(
            confirmations=v2_confirmation_service,
            drafts=draft_service,
            repository=repository,
        )
        v2_nodes = PMOMainGraphNodes(
            settings=app_settings,
            memory=memory_service,
            welcome=welcome_subgraph,
            status=status_subgraph,
            create_task=create_subgraph,
            update_task=update_subgraph,
            questions=QuestionsSubgraph(),
            confirmation=confirmation_subgraph,
        )
        v2_graph = build_pmo_agent_graph(v2_nodes)
        v2_locks = (
            RedisThreadLockManager(
                redis_url=app_settings.redis_url,
                ttl_seconds=app_settings.agent_thread_lock_ttl_seconds,
            )
            if app_settings.redis_enabled
            else ThreadLockManager(app_settings.agent_thread_lock_ttl_seconds)
        )
        app.state.agent_metrics = AgentMetrics()
        app.state.v2_agent_graph = v2_graph
        app.state.v2_agent_service = AgentV2Service(
            graph=v2_graph,
            repository=repository,
            settings=app_settings,
            thread_locks=v2_locks,
            tracer=tracer,
        )

        if not app_settings.llm_configured:
            logger.warning(
                "LLM is not fully configured. Set AI_PROVIDER plus provider API key and model."
            )
        else:
            logger.info(
                "LLM configured from environment: provider=%s model=%s",
                app_settings.llm_provider,
                app_settings.llm_model,
            )

        if not mcp_client.mcp_loaded:
            logger.warning("MCP board tools are not fully loaded: %s", mcp_client.registry.error)

        try:
            yield
        finally:
            await mcp_client.close()
            tracer.flush()

    api = FastAPI(title="PMO AI Agent API", version="0.2.0", lifespan=lifespan)
    install_correlation_middleware(api)
    api.include_router(admin_tenants_router)
    if route_settings.v1_endpoints_enabled:
        api.include_router(agent_v1_router)
    if route_settings.v2_endpoints_enabled:
        api.include_router(agent_v2_router)

    @api.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        app_settings: Settings = api.state.settings
        mcp_client: MCPBoardClient = api.state.mcp_client
        checks: dict[str, Any] = {
            "llm_provider": app_settings.llm_provider,
            "llm_configured": app_settings.llm_configured,
            "mcp_doc_path": app_settings.mcp_board_doc_path,
            "mcp_tool_count": len(mcp_client.registry.semantic_map),
        }
        if app_settings.llm_validate_model_on_health:
            checks["llm_model"] = await api.state.intent_service.check_llm_model()

        return HealthResponse(
            status="ok",
            service=app_settings.service_name,
            model=app_settings.llm_model or "not_configured",
            langfuse_enabled=api.state.tracer.enabled,
            mcp_loaded=mcp_client.mcp_loaded,
            checks=checks,
        )

    @api.get("/ready", response_model=HealthResponse)
    async def ready() -> HealthResponse:
        app_settings: Settings = api.state.settings
        mcp_client: MCPBoardClient = api.state.mcp_client
        tool_registry: ToolRegistry = api.state.tool_registry
        checks: dict[str, Any] = {
            "llm_provider": app_settings.llm_provider,
            "llm_configured": app_settings.llm_configured,
            "mcp_loaded": mcp_client.mcp_loaded,
            "registry_tools": sorted(tool_registry.names()),
            "database": "configured",
        }
        return HealthResponse(
            status="ok" if tool_registry.names() else "degraded",
            service=app_settings.service_name,
            model=app_settings.llm_model or "not_configured",
            langfuse_enabled=api.state.tracer.enabled,
            mcp_loaded=mcp_client.mcp_loaded,
            checks=checks,
        )

    @api.post("/agent/invoke", response_model=AgentInvokeResponse)
    async def agent_invoke(payload: AgentInvokeRequest) -> AgentInvokeResponse:
        if not route_settings.effective_legacy_endpoints_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legacy endpoint disabled")
        tracer: LangfuseTracer = api.state.tracer
        trace = tracer.start_trace(
            name="agent.invoke",
            session_id=payload.conversation_id,
            user_id=payload.user_id,
            metadata={
                "channel": payload.channel,
                "project_id": payload.metadata.get("project_id"),
            },
            input_payload=payload.model_dump(),
        )
        try:
            result = await api.state.invoke_graph.ainvoke(
                {
                    "conversation_id": payload.conversation_id,
                    "user_id": payload.user_id,
                    "channel": payload.channel,
                    "message": payload.message,
                    "request_metadata": payload.metadata,
                    "trace_id": trace.trace_id,
                    "_trace": trace,
                }
            )
            action = result.get("action")
            final_message = result.get("final_message") or ResponseService.error_response()
            response = AgentInvokeResponse(
                intent=result.get("intent", Intent.UNKNOWN),
                message=final_message,
                requires_confirmation=bool(result.get("requires_confirmation")),
                pending_action_id=result.get("pending_action_id"),
                action=AgentAction.model_validate(action) if action else None,
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response
        except Exception:
            logger.exception("Unhandled error in /agent/invoke")
            response = AgentInvokeResponse(
                intent=Intent.UNKNOWN,
                message=ResponseService.error_response(),
                requires_confirmation=False,
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response

    @api.post("/agent/process", response_model=ExternalAgentProcessResponse)
    async def agent_process(payload: ExternalAgentProcessRequest) -> ExternalAgentProcessResponse:
        """Compatibility endpoint for the existing PMO Agent ExternalAgentService contract."""
        if not route_settings.effective_legacy_endpoints_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legacy endpoint disabled")
        tracer: LangfuseTracer = api.state.tracer
        trace = tracer.start_trace(
            name="agent.process",
            session_id=payload.conversation_id,
            user_id=payload.user_id or "unknown",
            metadata={
                "compatibility": "external_agent_service",
                "project_id": payload.context.get("project_id") or payload.context.get("projectId"),
            },
            input_payload=payload.model_dump(),
        )
        try:
            classification = await api.state.intent_service.classify(payload.input_text, trace=trace)
            entities = {}
            if classification.intent in {
                Intent.TASK_CREATE,
                Intent.TASK_UPDATE,
                Intent.TASK_MOVE,
                Intent.TASK_COMMENT,
            }:
                extracted = await api.state.intent_service.extract_entities(
                    payload.input_text,
                    classification.intent,
                    trace=trace,
                )
                entities = extracted.model_dump(exclude_none=True)
            response = _build_external_agent_response(
                intent=classification.intent,
                confidence=classification.confidence,
                entities=entities,
                context=payload.context,
                input_text=payload.input_text,
            )
            tracer.update_trace(
                trace,
                metadata={
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "compatibility": "external_agent_service",
                },
                output=response.model_dump(mode="json"),
            )
            return response
        except Exception:
            logger.exception("Unhandled error in /agent/process")
            response = ExternalAgentProcessResponse(
                intent="unknown",
                confidence=0.0,
                requires_confirmation=False,
                response_text=ResponseService.error_response(),
                board_action=ExternalBoardAction(type="unknown", payload={}),
                missing_fields=[],
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response

    @api.post("/agent/confirm", response_model=AgentConfirmResponse)
    async def agent_confirm(payload: AgentConfirmRequest) -> AgentConfirmResponse:
        if not route_settings.effective_legacy_endpoints_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legacy endpoint disabled")
        tracer: LangfuseTracer = api.state.tracer
        trace = tracer.start_trace(
            name="agent.confirm",
            session_id=payload.conversation_id,
            user_id=payload.user_id,
            metadata={"confirmed": payload.confirmed},
            input_payload=payload.model_dump(),
        )
        try:
            result = await api.state.confirm_graph.ainvoke(
                {
                    "conversation_id": payload.conversation_id,
                    "user_id": payload.user_id,
                    "pending_action_id": payload.pending_action_id,
                    "confirmed": payload.confirmed,
                    "trace_id": trace.trace_id,
                    "_trace": trace,
                }
            )
            response = AgentConfirmResponse(
                message=result.get("final_message") or ResponseService.error_response(),
                executed=bool(result.get("executed")),
                board_result=result.get("board_result"),
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response
        except Exception:
            logger.exception("Unhandled error in /agent/confirm")
            response = AgentConfirmResponse(
                message=ResponseService.error_response(),
                executed=False,
                board_result=None,
            )
            tracer.update_trace(trace, output=response.model_dump(mode="json"))
            return response

    return api


app = create_app()


def _build_external_agent_response(
    *,
    intent: Intent,
    confidence: float,
    entities: dict[str, Any],
    context: dict[str, Any],
    input_text: str,
) -> ExternalAgentProcessResponse:
    legacy_intent = LEGACY_INTENT_BY_INTENT.get(intent, "unknown")
    action_type = _legacy_action_type(intent, input_text)
    missing_fields = _legacy_missing_fields(intent, entities)
    payload = _legacy_payload(intent, entities, context, input_text)

    requires_confirmation = intent in {
        Intent.TASK_CREATE,
        Intent.TASK_UPDATE,
        Intent.TASK_MOVE,
        Intent.TASK_COMMENT,
    } and not missing_fields

    return ExternalAgentProcessResponse(
        intent=legacy_intent,
        confidence=confidence,
        requires_confirmation=requires_confirmation,
        response_text=_legacy_response_text(intent, missing_fields),
        board_action=ExternalBoardAction(type=action_type, payload=payload),
        missing_fields=missing_fields,
    )


def _legacy_action_type(intent: Intent, input_text: str) -> str:
    text = input_text.casefold()
    if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION} and (
        "alerta" in text or "atras" in text or "bloque" in text
    ):
        return "query_alerts"
    return LEGACY_ACTION_BY_INTENT.get(intent, "unknown")


def _legacy_missing_fields(intent: Intent, entities: dict[str, Any]) -> list[str]:
    missing = []
    if intent == Intent.TASK_CREATE:
        if not entities.get("title"):
            missing.append("title")
    elif intent == Intent.TASK_UPDATE:
        if not (entities.get("task_id") or entities.get("task_query")):
            missing.append("task")
        if not entities.get("fields"):
            missing.append("fields")
    elif intent == Intent.TASK_MOVE:
        if not (entities.get("task_id") or entities.get("task_query")):
            missing.append("task")
        if not entities.get("status"):
            missing.append("status")
    elif intent == Intent.TASK_COMMENT:
        if not (entities.get("task_id") or entities.get("task_query")):
            missing.append("task")
        if not entities.get("comment"):
            missing.append("comment")
    return missing


def _legacy_payload(
    intent: Intent,
    entities: dict[str, Any],
    context: dict[str, Any],
    input_text: str,
) -> dict[str, Any]:
    project_id = context.get("project_id") or context.get("projectId")

    if intent == Intent.TASK_CREATE:
        return _drop_none(
            {
                "title": entities.get("title"),
                "description": entities.get("description") or entities.get("title"),
                "status": normalize_status(entities.get("status")) if entities.get("status") else None,
                "priority": normalize_priority(entities.get("priority")) if entities.get("priority") else None,
                "assigneeName": entities.get("assignee"),
                "dueDate": entities.get("due_date"),
                "projectId": project_id,
            }
        )

    if intent == Intent.TASK_UPDATE:
        fields = entities.get("fields") or {}
        normalized_fields = {
            key: normalize_priority(value) if key == "priority" else normalize_status(value) if key == "status" else value
            for key, value in fields.items()
        }
        return _drop_none(
            {
                "taskId": entities.get("task_id"),
                "taskQuery": entities.get("task_query"),
                "fields": normalized_fields,
                "projectId": project_id,
            }
        )

    if intent == Intent.TASK_MOVE:
        return _drop_none(
            {
                "taskId": entities.get("task_id"),
                "taskQuery": entities.get("task_query"),
                "status": normalize_status(entities.get("status")) if entities.get("status") else None,
                "projectId": project_id,
            }
        )

    if intent == Intent.TASK_COMMENT:
        return _drop_none(
            {
                "taskId": entities.get("task_id"),
                "taskQuery": entities.get("task_query"),
                "comment": entities.get("comment"),
                "projectId": project_id,
            }
        )

    if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION}:
        return _drop_none({"query": input_text, "projectId": project_id})

    return {}


def _legacy_response_text(intent: Intent, missing_fields: list[str]) -> str:
    if missing_fields:
        if "title" in missing_fields:
            return "Qual e o titulo da atividade?"
        if "task" in missing_fields:
            return "Qual atividade voce quer alterar? Envie o ID ou o titulo."
        if "status" in missing_fields:
            return "Para qual status voce quer mover essa atividade?"
        if "comment" in missing_fields:
            return "Qual comentario voce quer adicionar?"
        if "fields" in missing_fields:
            return "O que voce quer atualizar nessa atividade?"
        return "Preciso de mais detalhes para continuar."

    if intent == Intent.TASK_CREATE:
        return "Confirma a criacao da atividade?"
    if intent == Intent.TASK_UPDATE:
        return "Confirma a atualizacao da atividade?"
    if intent == Intent.TASK_MOVE:
        return "Confirma a movimentacao da atividade?"
    if intent == Intent.TASK_COMMENT:
        return "Confirma a inclusao do comentario?"
    if intent in {Intent.STATUS_BOARD, Intent.BOARD_QUESTION}:
        return "Vou consultar as atividades do board."
    if intent == Intent.SMALLTALK:
        return "Posso ajudar com status, criacao ou atualizacao de atividades."
    return "Nao entendi bem. Pode reformular?"


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}

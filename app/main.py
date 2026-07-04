from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.graph.builder import build_confirmation_graph, build_invoke_graph
from app.graph.nodes import AgentGraphNodes
from app.mcp.board_tools import BoardTools
from app.mcp.client import MCPBoardClient
from app.observability.langfuse import LangfuseTracer
from app.schemas import (
    AgentAction,
    AgentConfirmRequest,
    AgentConfirmResponse,
    AgentInvokeRequest,
    AgentInvokeResponse,
    HealthResponse,
    Intent,
)
from app.services.confirmation_service import ConfirmationService
from app.services.intent_service import IntentService
from app.services.pending_action_service import PendingActionService
from app.services.response_service import ResponseService
from app.storage.repository import PendingActionRepository

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    board_tools_override: Any | None = None,
    repository_override: PendingActionRepository | None = None,
) -> FastAPI:
    settings_override = settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings = settings_override or get_settings()
        logging.basicConfig(
            level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

        repository = repository_override or PendingActionRepository(app_settings)
        repository.init_db()

        mcp_client = MCPBoardClient(app_settings)
        board_tools = board_tools_override or BoardTools(mcp_client)
        tracer = LangfuseTracer(app_settings)
        intent_service = IntentService(app_settings)
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
        app.state.mcp_client = mcp_client
        app.state.board_tools = board_tools
        app.state.tracer = tracer
        app.state.intent_service = intent_service
        app.state.invoke_graph = build_invoke_graph(nodes)
        app.state.confirm_graph = build_confirmation_graph(nodes)

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
            tracer.flush()

    api = FastAPI(title="PMO AI Agent API", version="0.1.0", lifespan=lifespan)

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

    @api.post("/agent/invoke", response_model=AgentInvokeResponse)
    async def agent_invoke(payload: AgentInvokeRequest) -> AgentInvokeResponse:
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

    @api.post("/agent/confirm", response_model=AgentConfirmResponse)
    async def agent_confirm(payload: AgentConfirmRequest) -> AgentConfirmResponse:
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

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.agent.state import AgentState
from app.api.dependencies import RequestContext, get_request_context
from app.api.schemas.agent_v1 import (
    AgentConfirmationRequest,
    AgentMessageRequest,
    AgentV1Response,
)


router = APIRouter(prefix="/v1/agent", tags=["agent-v1"])


@router.post("/messages", response_model=AgentV1Response)
async def post_message(
    payload: AgentMessageRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> AgentV1Response:
    state: AgentState = {
        "request_id": context.request_id,
        "correlation_id": context.correlation_id,
        "thread_id": payload.thread_id,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "user_roles": context.user_roles,
        "channel": payload.channel,
        "metadata": payload.metadata,
        "original_message": payload.message,
    }
    result = await request.app.state.v1_agent_service.handle_message(state)
    return AgentV1Response.model_validate(result)


@router.post("/confirmations", response_model=AgentV1Response)
async def post_confirmation(
    payload: AgentConfirmationRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> AgentV1Response:
    result = await request.app.state.v1_agent_service.handle_confirmation(
        request_id=context.request_id,
        correlation_id=context.correlation_id,
        thread_id=payload.thread_id,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        user_roles=context.user_roles,
        confirmation_id=payload.confirmation_id,
        approved=payload.approved,
        message=payload.message,
    )
    return AgentV1Response.model_validate(result)


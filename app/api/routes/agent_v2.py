from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import (
    RequestContext,
    get_admin_request_context,
    get_authenticated_request_context,
)
from app.api.schemas.agent_v2 import AgentEventEnvelope, AgentThreadSnapshot, AgentV2Response


router = APIRouter(prefix="/v2/agent", tags=["agent-v2"])


@router.post("/events", response_model=AgentV2Response)
async def post_event(
    payload: AgentEventEnvelope,
    request: Request,
    context: RequestContext = Depends(get_authenticated_request_context),
) -> AgentV2Response:
    if payload.message_type == "confirmation":
        request.app.state.agent_metrics.increment("agent_confirmations_total", api_version="v2")
    return await request.app.state.v2_agent_service.handle_event(payload, context)


@router.get("/threads/{thread_id}", response_model=AgentThreadSnapshot)
async def get_thread(
    thread_id: str,
    request: Request,
    context: RequestContext = Depends(get_admin_request_context),
) -> AgentThreadSnapshot:
    snapshot = await request.app.state.v2_agent_service.get_thread(
        tenant_id=context.tenant_id,
        thread_id=thread_id,
    )
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return snapshot

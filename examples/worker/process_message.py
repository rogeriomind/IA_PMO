from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from pmo_agent_client import PMOAgentClient


agent_client = PMOAgentClient(
    base_url=os.getenv("PMO_AGENT_API_URL", "http://agent-api:8010"),
    token=os.getenv("PMO_AGENT_API_TOKEN") or None,
    timeout_seconds=float(os.getenv("PMO_AGENT_TIMEOUT_SECONDS", "30")),
    max_retries=int(os.getenv("PMO_AGENT_MAX_RETRIES", "2")),
    verify_ssl=os.getenv("PMO_AGENT_VERIFY_SSL", "true").casefold() == "true",
)


async def process_message(queue_message: dict[str, Any]) -> None:
    request_id = queue_message.get("request_id") or str(uuid4())
    correlation_id = queue_message.get("correlation_id") or request_id
    tenant_id = queue_message["tenant_id"]
    channel = queue_message["channel"]
    conversation_id = queue_message["conversation_id"]
    thread_id = f"{tenant_id}:{channel}:{conversation_id}"

    result = await agent_client.send_message(
        thread_id=thread_id,
        message=queue_message["message"],
        channel=channel,
        metadata={
            "message_id": queue_message["message_id"],
            "conversation_id": conversation_id,
            "source": "worker",
            **queue_message.get("metadata", {}),
        },
        request_id=request_id,
        correlation_id=correlation_id,
    )

    status = result.get("status")
    if status == "completed":
        await send_channel_message(channel=channel, destination=conversation_id, message=result["message"])
        return
    if status == "awaiting_confirmation":
        await save_pending_confirmation(thread_id=thread_id, confirmation=result["confirmation"])
        await send_channel_message(channel=channel, destination=conversation_id, message=result["message"])
        return
    if status == "rejected":
        await send_channel_message(channel=channel, destination=conversation_id, message=result["message"])
        return
    if status == "error":
        await handle_agent_error(queue_message=queue_message, result=result)
        return
    raise RuntimeError(f"Status desconhecido retornado pelo agente: {status}")


async def send_channel_message(*, channel: str, destination: str, message: str) -> None:
    raise NotImplementedError("Conecte este stub ao provedor do canal.")


async def save_pending_confirmation(*, thread_id: str, confirmation: dict[str, Any]) -> None:
    raise NotImplementedError("Persista confirmation_id e thread_id no storage do worker.")


async def handle_agent_error(*, queue_message: dict[str, Any], result: dict[str, Any]) -> None:
    raise NotImplementedError("Aplique a politica de erro/retry/dead-letter do worker.")


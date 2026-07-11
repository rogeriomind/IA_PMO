import pytest
import httpx

import examples.worker.pmo_agent_client as worker_client
from examples.worker.pmo_agent_client import (
    PMOAgentClient,
    PMOAgentInvalidResponseError,
    PMOAgentUnavailableError,
)


@pytest.mark.asyncio
async def test_worker_client_sends_message_with_correlation_headers(monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["json"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "thread_id": "porto:telegram:123",
                "status": "completed",
                "message": "ok",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://agent")
    agent = PMOAgentClient(base_url="http://agent", client=client)

    result = await agent.send_message(
        thread_id="porto:telegram:123",
        message="Minhas tarefas",
        channel="telegram",
        metadata={"message_id": "m1"},
        request_id="req-1",
        correlation_id="corr-1",
    )

    assert result["status"] == "completed"
    assert captured["headers"]["X-Request-ID"] == "req-1"
    assert captured["headers"]["X-Correlation-ID"] == "corr-1"
    assert '"thread_id":"porto:telegram:123"' in captured["json"].replace(" ", "")
    await agent.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_worker_client_retries_transient_message(monkeypatch):
    monkeypatch.setattr(worker_client, "_backoff_seconds", lambda attempt: 0)
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "thread_id": "porto:telegram:123",
                "status": "completed",
                "message": "ok",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://agent")
    agent = PMOAgentClient(base_url="http://agent", client=client, max_retries=1)

    result = await agent.send_message(
        thread_id="porto:telegram:123",
        message="Minhas tarefas",
        channel="telegram",
        metadata={},
        request_id="req-1",
        correlation_id="corr-1",
    )

    assert result["status"] == "completed"
    assert calls["count"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_worker_client_does_not_retry_confirmation():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"error": "temporary"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://agent")
    agent = PMOAgentClient(base_url="http://agent", client=client, max_retries=2)

    with pytest.raises(PMOAgentUnavailableError):
        await agent.confirm_action(
            thread_id="porto:telegram:123",
            confirmation_id="conf-1",
            approved=True,
            request_id="req-1",
            correlation_id="corr-1",
            message="confirmo",
        )

    assert calls["count"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_worker_client_rejects_invalid_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "a", "dict"])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://agent")
    agent = PMOAgentClient(base_url="http://agent", client=client)

    with pytest.raises(PMOAgentInvalidResponseError):
        await agent.send_message(
            thread_id="porto:telegram:123",
            message="Minhas tarefas",
            channel="telegram",
            metadata={},
            request_id="req-1",
            correlation_id="corr-1",
        )

    await client.aclose()


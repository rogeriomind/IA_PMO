from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx


TRANSIENT_STATUS_CODES = {408, 429, 502, 503, 504}


class PMOAgentClientError(Exception):
    pass


class PMOAgentTimeoutError(PMOAgentClientError):
    pass


class PMOAgentUnavailableError(PMOAgentClientError):
    pass


class PMOAgentInvalidResponseError(PMOAgentClientError):
    pass


class PMOAgentClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout_seconds: float = 30,
        max_retries: int = 2,
        verify_ssl: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.max_retries = max(0, max_retries)
        self._owns_client = client is None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify_ssl,
        )

    async def send_message(
        self,
        *,
        thread_id: str,
        message: str,
        channel: str,
        metadata: dict[str, Any],
        request_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return await self._request_with_retry(
            "POST",
            "/v1/agent/messages",
            headers=self._correlation_headers(request_id, correlation_id),
            json={
                "thread_id": thread_id,
                "message": message,
                "channel": channel,
                "metadata": metadata,
            },
        )

    async def confirm_action(
        self,
        *,
        thread_id: str,
        confirmation_id: str,
        approved: bool,
        request_id: str,
        correlation_id: str,
        message: str | None = None,
    ) -> dict[str, Any]:
        return await self._request_once(
            "POST",
            "/v1/agent/confirmations",
            headers=self._correlation_headers(request_id, correlation_id),
            json={
                "thread_id": thread_id,
                "confirmation_id": confirmation_id,
                "approved": approved,
                "message": message,
            },
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self._request_once(method, url, **kwargs)
            except PMOAgentTimeoutError as exc:
                last_error = exc
            except PMOAgentUnavailableError as exc:
                last_error = exc
            if attempt >= self.max_retries:
                break
            await asyncio.sleep(_backoff_seconds(attempt))
        raise last_error or PMOAgentUnavailableError("Agent API unavailable")

    async def _request_once(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise PMOAgentTimeoutError("Agent API request timed out") from exc
        except httpx.TransportError as exc:
            raise PMOAgentUnavailableError("Agent API transport error") from exc

        if response.status_code in TRANSIENT_STATUS_CODES:
            raise PMOAgentUnavailableError(f"Agent API transient HTTP {response.status_code}")
        if response.is_error:
            raise PMOAgentClientError(f"Agent API HTTP {response.status_code}: {response.text[:300]}")

        try:
            data = response.json()
        except ValueError as exc:
            raise PMOAgentInvalidResponseError("Agent API returned invalid JSON") from exc
        if not isinstance(data, dict) or "status" not in data or "request_id" not in data:
            raise PMOAgentInvalidResponseError("Agent API response schema is invalid")
        return data

    @staticmethod
    def _correlation_headers(request_id: str, correlation_id: str) -> dict[str, str]:
        return {
            "X-Request-ID": request_id,
            "X-Correlation-ID": correlation_id,
        }


def _backoff_seconds(attempt: int) -> float:
    base = 1.0 if attempt == 0 else 3.0
    return base + random.uniform(0, 0.25)


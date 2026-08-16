from __future__ import annotations

import time
from uuid import uuid4

from fastapi import FastAPI, Request

from app.infrastructure.observability.metrics import AgentMetrics


def install_correlation_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        start = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        api_version = _agent_api_version(request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = int((time.perf_counter() - start) * 1000)
            _record_agent_request_metrics(request, api_version, latency_ms, is_error=True)
            raise
        latency_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = str(latency_ms)
        _record_agent_request_metrics(
            request,
            api_version,
            latency_ms,
            is_error=response.status_code >= 400,
        )
        return response


def _agent_api_version(path: str) -> str | None:
    if path in {"/agent/invoke", "/agent/process", "/agent/confirm"}:
        return "legacy"
    if path.startswith("/v1/agent/"):
        return "v1"
    if path.startswith("/v2/agent/"):
        return "v2"
    return None


def _record_agent_request_metrics(
    request: Request,
    api_version: str | None,
    latency_ms: int,
    *,
    is_error: bool,
) -> None:
    if not api_version:
        return
    metrics = getattr(request.app.state, "agent_metrics", None)
    if not isinstance(metrics, AgentMetrics):
        return
    metrics.increment("agent_requests_total", api_version=api_version)
    metrics.observe("agent_latency_ms", latency_ms, api_version=api_version)
    if is_error:
        metrics.increment("agent_errors_total", api_version=api_version)

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx


BREAKDOWN_KEYS = (
    "agent_total_ms",
    "routing_ms",
    "subgraph_ms",
    "llm_ms",
    "mcp_ms",
    "memory_load_ms",
    "memory_persist_ms",
)


@dataclass
class ScenarioResult:
    totals: list[int] = field(default_factory=list)
    breakdowns: dict[str, list[int]] = field(default_factory=lambda: {key: [] for key in BREAKDOWN_KEYS})

    def add(self, elapsed_ms: int, latency: dict[str, Any]) -> None:
        total = int(latency.get("agent_total_ms") or elapsed_ms)
        self.totals.append(total)
        for key in BREAKDOWN_KEYS:
            value = latency.get(key)
            if isinstance(value, int | float):
                self.breakdowns[key].append(int(value))


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summary(values: list[int]) -> dict[str, int]:
    if not values:
        return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0}
    return {
        "p50": int(statistics.median(values)),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
    }


class AgentBenchmark:
    def __init__(self, *, base_url: str, token: str, tenant_id: str, user_id: str, project_id: str | None):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
            "X-User-ID": user_id,
            "X-User-Roles": os.getenv("AGENT_BENCH_USER_ROLES", "board.read,board.write,board.manage"),
        }
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.project_id = project_id

    async def post_event(
        self,
        client: httpx.AsyncClient,
        *,
        thread_id: str,
        message_type: str,
        text: str | None = None,
        callback_data: str | None = None,
        measured: bool = True,
    ) -> tuple[dict[str, Any], int]:
        event_id = str(uuid4())
        payload = {
            "event_id": event_id,
            "request_id": f"bench-{event_id}",
            "correlation_id": f"bench-{event_id}",
            "thread_id": thread_id,
            "tenant_id": self.tenant_id,
            "channel": "benchmark",
            "message_type": message_type,
            "user": {"id": self.user_id, "name": "Benchmark", "username": "benchmark"},
            "content": {"text": text, "callback_data": callback_data},
            "metadata": {
                "project_id": self.project_id,
                "timezone": os.getenv("AGENT_BENCH_TIMEZONE", "America/Sao_Paulo"),
            },
        }
        started = time.perf_counter()
        response = await client.post("/v2/agent/events", json=payload, headers=self.headers)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        body = response.json()
        if measured and body.get("status") == "error":
            raise RuntimeError(body.get("error") or body)
        return body, elapsed_ms

    async def status(self, client: httpx.AsyncClient, index: int) -> tuple[dict[str, Any], int]:
        return await self.post_event(
            client,
            thread_id=f"bench-status-{index}-{uuid4()}",
            message_type="menu_selection",
            callback_data="menu:status",
        )

    async def get_task(self, client: httpx.AsyncClient, index: int) -> tuple[dict[str, Any], int]:
        thread_id = f"bench-get-{index}-{uuid4()}"
        status, _ = await self.post_event(
            client,
            thread_id=thread_id,
            message_type="menu_selection",
            callback_data="menu:status",
            measured=False,
        )
        task_callback = _first_task_callback(status) or "status:task:1"
        return await self.post_event(
            client,
            thread_id=thread_id,
            message_type="task_selection",
            callback_data=task_callback,
        )

    async def create_preview(self, client: httpx.AsyncClient, index: int) -> tuple[dict[str, Any], int]:
        return await self.post_event(
            client,
            thread_id=f"bench-create-preview-{index}-{uuid4()}",
            message_type="text",
            text=f"Criar atividade Benchmark preview {index} para amanha, prioridade baixa.",
        )

    async def create_confirmation(self, client: httpx.AsyncClient, index: int) -> tuple[dict[str, Any], int]:
        thread_id = f"bench-create-confirm-{index}-{uuid4()}"
        preview, _ = await self.post_event(
            client,
            thread_id=thread_id,
            message_type="text",
            text=f"Criar atividade Benchmark confirmacao {index} para amanha, prioridade baixa.",
            measured=False,
        )
        confirmation_id = (preview.get("confirmation") or {}).get("id")
        if not confirmation_id:
            raise RuntimeError(f"Preview did not return confirmation: {preview}")
        return await self.post_event(
            client,
            thread_id=thread_id,
            message_type="confirmation",
            callback_data=f"confirmation:approve:{confirmation_id}",
        )

    async def update_preview(self, client: httpx.AsyncClient, index: int, task_id: str) -> tuple[dict[str, Any], int]:
        thread_id = f"bench-update-preview-{index}-{uuid4()}"
        await self.post_event(
            client,
            thread_id=thread_id,
            message_type="menu_selection",
            callback_data="menu:update",
            measured=False,
        )
        await self.post_event(
            client,
            thread_id=thread_id,
            message_type="text",
            text=task_id,
            measured=False,
        )
        return await self.post_event(
            client,
            thread_id=thread_id,
            message_type="text",
            text=f"Adicione comentario Benchmark preview {index}",
        )

    async def update_confirmation(self, client: httpx.AsyncClient, index: int, task_id: str) -> tuple[dict[str, Any], int]:
        thread_id = f"bench-update-confirm-{index}-{uuid4()}"
        await self.post_event(
            client,
            thread_id=thread_id,
            message_type="menu_selection",
            callback_data="menu:update",
            measured=False,
        )
        await self.post_event(
            client,
            thread_id=thread_id,
            message_type="text",
            text=task_id,
            measured=False,
        )
        preview, _ = await self.post_event(
            client,
            thread_id=thread_id,
            message_type="text",
            text=f"Adicione comentario Benchmark confirmacao {index}",
            measured=False,
        )
        confirmation_id = (preview.get("confirmation") or {}).get("id")
        if not confirmation_id:
            raise RuntimeError(f"Update preview did not return confirmation: {preview}")
        return await self.post_event(
            client,
            thread_id=thread_id,
            message_type="confirmation",
            callback_data=f"confirmation:approve:{confirmation_id}",
        )


async def run(args: argparse.Namespace) -> None:
    token = args.token or os.getenv("AGENT_API_TOKEN")
    if not token:
        raise SystemExit("Set AGENT_API_TOKEN or pass --token.")

    benchmark = AgentBenchmark(
        base_url=args.base_url,
        token=token,
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        project_id=args.project_id,
    )
    results: dict[str, ScenarioResult] = {}
    timeout = httpx.Timeout(args.timeout_seconds)
    async with httpx.AsyncClient(base_url=benchmark.base_url, timeout=timeout) as client:
        scenarios = [
            ("status", lambda i: benchmark.status(client, i)),
            ("board_get_task", lambda i: benchmark.get_task(client, i)),
            ("create_preview", lambda i: benchmark.create_preview(client, i)),
        ]
        if args.task_id:
            scenarios.append(("update_preview", lambda i: benchmark.update_preview(client, i, args.task_id)))
        if args.include_writes:
            scenarios.append(("create_confirmation", lambda i: benchmark.create_confirmation(client, i)))
            if args.task_id:
                scenarios.append(("update_confirmation", lambda i: benchmark.update_confirmation(client, i, args.task_id)))

        for name, scenario in scenarios:
            bucket = results.setdefault(name, ScenarioResult())
            for index in range(args.runs):
                body, elapsed_ms = await scenario(index)
                latency = (body.get("data") or {}).get("latency") or {}
                bucket.add(elapsed_ms, latency)

    print(
        "scenario,mcp_transport,total_p50,total_p90,total_p95,total_p99,total_max,"
        "langgraph_p95,llm_p95,mcp_p95,memory_p95"
    )
    for name, bucket in results.items():
        total = summary(bucket.totals)
        subgraph = summary(bucket.breakdowns["subgraph_ms"])
        llm = summary(bucket.breakdowns["llm_ms"])
        mcp = summary(bucket.breakdowns["mcp_ms"])
        memory_values = bucket.breakdowns["memory_load_ms"] + bucket.breakdowns["memory_persist_ms"]
        memory = summary(memory_values)
        print(
            f"{name},{args.mcp_transport},{total['p50']},{total['p90']},{total['p95']},{total['p99']},{total['max']},"
            f"{subgraph['p95']},{llm['p95']},{mcp['p95']},{memory['p95']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark /v2/agent/events latency.")
    parser.add_argument("--base-url", default=os.getenv("AGENT_BENCH_BASE_URL", "http://localhost:8010"))
    parser.add_argument("--token", default=None)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--tenant-id", default=os.getenv("AGENT_BENCH_TENANT_ID", "default"))
    parser.add_argument("--user-id", default=os.getenv("AGENT_BENCH_USER_ID", "benchmark"))
    parser.add_argument("--project-id", default=os.getenv("AGENT_BENCH_PROJECT_ID"))
    parser.add_argument("--task-id", default=os.getenv("AGENT_BENCH_TASK_ID"))
    parser.add_argument("--mcp-transport", default=os.getenv("MCP_BOARD_TRANSPORT", "unknown"))
    parser.add_argument("--include-writes", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args()


def _first_task_callback(response: dict[str, Any]) -> str | None:
    ui = response.get("ui") or {}
    for option in ui.get("options") or []:
        callback = option.get("callback_data")
        if isinstance(callback, str) and callback.startswith(("status:id:", "status:task:")):
            return callback
    return None


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

from __future__ import annotations

from typing import Any

from app.agent.context import ToolExecutionContext
from app.agent.intents import INTENT_TO_TOOL
from app.agent.mcp_gateway import MCPGateway
from app.agent.state import AgentState


class ProjectNodes:
    def __init__(self, gateway: MCPGateway):
        self.gateway = gateway

    async def resolve_project(self, state: AgentState) -> AgentState:
        entities = state.get("entities") or {}
        metadata = state.get("metadata") or {}
        project_id = entities.get("project_id") or metadata.get("project_id") or metadata.get("projectId")
        return {"tool_input": {"project_id": project_id} if project_id else {}}

    async def select_project_tool(self, state: AgentState) -> AgentState:
        return {"selected_tool": INTENT_TO_TOOL[state.get("intent", "project.status")]}

    async def execute_tool(self, state: AgentState) -> AgentState:
        result = await self.gateway.execute(
            tool_name=state["selected_tool"],
            arguments=state.get("tool_input") or {},
            context=ToolExecutionContext(
                request_id=state["request_id"],
                correlation_id=state["correlation_id"],
                thread_id=state["thread_id"],
                tenant_id=state["tenant_id"],
                user_id=state["user_id"],
                user_roles=state.get("user_roles") or [],
                intent=state.get("intent", "project.status"),
                approval_status="not_required",
            ),
        )
        return {"tool_result": result.model_dump(), "data": {"result": result.result}}

    async def normalize_project_data(self, state: AgentState) -> AgentState:
        return {}

    async def generate_executive_summary(self, state: AgentState) -> AgentState:
        result = (state.get("tool_result") or {}).get("result")
        if state.get("intent") == "project.blockers":
            return {"final_answer": _format_blockers(result), "status": "completed"}
        return {"final_answer": _format_status(result), "status": "completed"}


def _format_status(result: Any) -> str:
    if isinstance(result, dict):
        lines = []
        for key, label in (
            ("status", "Status"),
            ("progress", "Andamento"),
            ("open_tasks", "Tarefas abertas"),
            ("blockers", "Bloqueios"),
            ("next_steps", "Proximos passos"),
        ):
            value = result.get(key)
            if value:
                lines.append(f"{label}: {value}")
        if lines:
            return "\n".join(lines)
    return f"Status do projeto: {result}"


def _format_blockers(result: Any) -> str:
    if isinstance(result, list):
        if not result:
            return "Nao encontrei bloqueios no projeto."
        return "Bloqueios encontrados:\n" + "\n".join(f"- {item}" for item in result[:5])
    if isinstance(result, dict):
        blockers = result.get("blockers") or result.get("items") or result.get("data")
        if isinstance(blockers, list):
            return _format_blockers(blockers)
    return f"Bloqueios do projeto: {result}"


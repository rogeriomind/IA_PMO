from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

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
                api_version=state.get("api_version", "v1"),
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
        lines.append("📊 *Status do projeto*")
        lines.append("")

        total_tasks = result.get("totalTasks") or result.get("total_tasks")
        active_tasks = result.get("activeTasks") or result.get("active_tasks")
        completed_tasks = result.get("completedTasks") or result.get("completed_tasks")
        completion_rate = result.get("completionRate") or result.get("completion_rate")

        if total_tasks is not None:
            lines.append(f"📌 *Total de tarefas:* {total_tasks}")
        if active_tasks is not None:
            lines.append(f"🔄 *Ativas:* {active_tasks}")
        if completed_tasks is not None:
            lines.append(f"✅ *Concluídas:* {completed_tasks}")
        if completion_rate is not None:
            lines.append(f"📈 *Conclusão:* {completion_rate}%")

        overdue = result.get("overdue")
        if isinstance(overdue, dict) and overdue.get("count"):
            lines.append(f"⚠️ *Vencidas:* {overdue.get('count')}")

        blockers = result.get("blockers")
        if isinstance(blockers, dict) and blockers.get("count"):
            lines.append(f"🚨 *Bloqueios:* {blockers.get('count')}")

        if len(lines) > 2:
            if isinstance(blockers, dict) and blockers.get("tasks"):
                lines.append("")
                lines.append(_format_blockers(blockers))
            return "\n".join(lines)

        for key, label in (
            ("status", "📌 *Status*"),
            ("progress", "📈 *Andamento*"),
            ("open_tasks", "📋 *Tarefas abertas*"),
            ("next_steps", "➡️ *Próximos passos*"),
        ):
            value = result.get(key)
            if value:
                lines.append(f"{label}: {value}")
        if lines:
            return "\n".join(lines)
    return f"Status do projeto: {result}"


def _format_blockers(result: Any) -> str:
    tasks = _extract_blocker_tasks(result)
    count = _extract_blocker_count(result, tasks)
    if not tasks:
        return "✅ *Bloqueios do projeto*\n\nNão encontrei bloqueios no projeto."

    plural = "bloqueio" if count == 1 else "bloqueios"
    attention = "precisa" if count == 1 else "precisam"
    lines = [
        "🚨 *Bloqueios do projeto*",
        "",
        f"Foi identificado *{count} {plural}* que {attention} de atenção.",
        "",
        "━━━━━━━━━━━━━━",
        "",
    ]

    for index, task in enumerate(tasks[:5]):
        if index:
            lines.extend(["", "━━━━━━━━━━━━━━", ""])
        lines.extend(_format_blocker_task(task))

    remaining = count - len(tasks[:5])
    if remaining > 0:
        lines.extend(["", f"… e mais *{remaining}* bloqueios."])
    return "\n".join(lines)


def _extract_blocker_tasks(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [task for task in result if isinstance(task, dict)]
    if isinstance(result, dict):
        blockers = result.get("blockers") or result.get("items") or result.get("data") or result.get("tasks")
        if isinstance(blockers, dict):
            tasks = blockers.get("tasks") or blockers.get("items") or blockers.get("data")
            if isinstance(tasks, list):
                return [task for task in tasks if isinstance(task, dict)]
        if isinstance(blockers, list):
            return [task for task in blockers if isinstance(task, dict)]
    return []


def _extract_blocker_count(result: Any, tasks: list[dict[str, Any]]) -> int:
    if isinstance(result, dict):
        if isinstance(result.get("count"), int):
            return result["count"]
        blockers = result.get("blockers")
        if isinstance(blockers, dict) and isinstance(blockers.get("count"), int):
            return blockers["count"]
    return len(tasks)


def _format_blocker_task(task: dict[str, Any]) -> list[str]:
    title = task.get("title") or task.get("name") or task.get("id") or "Tarefa sem título"
    lines = [f"🔴 *{title}*", ""]

    status = _format_status_value(task.get("status"))
    if status:
        lines.append(f"📌 *Status:* {status}")

    priority = _format_priority(task.get("priority"))
    if priority:
        lines.append(f"⚡ *Prioridade:* {priority}")

    assignee = _format_assignee(task.get("assignee") or task.get("assigneeName"))
    if assignee:
        lines.append(f"👤 *Responsável:* {assignee}")

    due_date = _format_due_date(task.get("dueDate") or task.get("due_date"))
    if due_date:
        lines.append(f"📅 *Prazo:* {due_date}")

    blocked_reason = task.get("blockedReason") or task.get("blocked_reason") or task.get("reason")
    if blocked_reason:
        lines.append(f"⛔ *Motivo:* {blocked_reason}")

    tags = _format_tags(task.get("tags"))
    if tags:
        lines.append(f"🏷️ *Tags:* {tags}")

    return lines


def _format_status_value(value: Any) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().upper()
    return {
        "BACKLOG": "Backlog",
        "TODO": "A fazer",
        "IN_PROGRESS": "Em andamento",
        "BLOCKED": "Bloqueada",
        "IN_REVIEW": "Em revisão",
        "DONE": "Concluída",
        "CANCELED": "Cancelada",
        "CANCELLED": "Cancelada",
    }.get(normalized, str(value))


def _format_priority(value: Any) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().upper()
    return {
        "LOW": "Baixa",
        "MEDIUM": "Média",
        "HIGH": "Alta",
        "CRITICAL": "Crítica",
    }.get(normalized, str(value))


def _format_assignee(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        return value.get("name") or value.get("email") or value.get("id")
    return str(value)


def _format_due_date(value: Any) -> str | None:
    parsed = _parse_date(value)
    if not parsed:
        return str(value) if value else None
    formatted = parsed.strftime("%d/%m/%Y")
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    if parsed < today:
        return f"{formatted} — ⚠️ Vencido"
    if parsed == today:
        return f"{formatted} — vence hoje"
    return formatted


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _format_tags(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    names.append(str(name))
            elif item:
                names.append(str(item))
        return ", ".join(names) if names else None
    return str(value)

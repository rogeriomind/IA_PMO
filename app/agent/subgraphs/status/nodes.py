from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.agent.context import ToolExecutionContext
from app.agent.errors import AgentError
from app.agent.main_graph.state import PMOAgentState
from app.agent.mcp_gateway import MCPGateway
from app.agent.subgraphs.common import (
    extract_tasks,
    first_int,
    format_date_br,
    inline_keyboard,
    numbered_list,
    parse_iso_date,
    task_due_date,
    task_id,
    task_priority,
    task_title,
)
from app.application.task_selection_service import TaskSelectionService
from app.config import Settings


class StatusSubgraph:
    def __init__(self, *, gateway: MCPGateway, selections: TaskSelectionService, settings: Settings):
        self.gateway = gateway
        self.selections = selections
        self.settings = settings

    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        callback = state.get("callback_data") or ""
        number = _selected_number(state)
        if callback == "status:update_task":
            return {
                "current_flow": "task_update",
                "current_step": "waiting_update_fields",
                "final_message": "O que voc\u00ea deseja atualizar nessa atividade?\n\nVoc\u00ea pode alterar a data, o respons\u00e1vel ou adicionar um coment\u00e1rio.",
                "response_ui": inline_keyboard(
                    [
                        {"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"},
                    ]
                ),
                "response_status": "waiting_user_input",
            }
        if number is not None:
            return await self._show_task_detail(state, number)
        return await self._show_status_list(state)

    async def _show_status_list(self, state: PMOAgentState) -> PMOAgentState:
        today = _today(state)
        project_id = (state.get("metadata") or {}).get("project_id")
        try:
            my_tasks_result, blockers_result = await asyncio.gather(
                self.gateway.execute(
                    tool_name="board_list_my_tasks",
                    arguments={"user_id": state["user_id"], "project_id": project_id},
                    context=_context(state, intent="user.my_tasks"),
                ),
                self.gateway.execute(
                    tool_name="board_list_blockers",
                    arguments={"project_id": project_id},
                    context=_context(state, intent="project.blockers"),
                ),
            )
        except AgentError as exc:
            return {
                "current_flow": "status",
                "current_step": "status_error",
                "final_message": exc.user_message,
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "degraded",
                "error_code": exc.code,
                "error_message": exc.user_message,
            }

        tasks = _combine_tasks(extract_tasks(my_tasks_result.result), extract_tasks(blockers_result.result))
        categorized = _categorize_tasks(tasks, today)
        visible_tasks = categorized["blocked"] + categorized["overdue"] + categorized["today"]
        await self.selections.replace_map(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="status",
            tasks=visible_tasks,
        )

        if not visible_tasks:
            return {
                "current_flow": "status",
                "current_step": "waiting_status_action",
                "task_selection_map": {},
                "final_message": "Voc\u00ea n\u00e3o possui atividades atrasadas, bloqueadas ou previstas para hoje. \u2705",
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "waiting_user_input",
                "response_data": {"tasks": []},
            }

        lines = ["\U0001f4ca Seu status de atividades"]
        options: list[dict[str, str]] = []
        index = 1
        for section_key, title in [
            ("blocked", "\U0001f534 Bloqueadas"),
            ("overdue", "\u23f0 Atrasadas"),
            ("today", "\U0001f4c5 Para hoje"),
        ]:
            section_tasks = categorized[section_key]
            if not section_tasks:
                continue
            lines.extend(["", title])
            for task in section_tasks:
                due = format_date_br(task_due_date(task), today)
                title_text = task_title(task)
                lines.append(f"{index}. {title_text} - vencimento {due}")
                options.append(
                    {
                        "id": f"status_task_{index}",
                        "label": f"{index}. {title_text}",
                        "callback_data": f"status:task:{index}",
                    }
                )
                index += 1
        options.extend(
            [
                {
                    "id": "status_update_task",
                    "label": "Atualizar atividade",
                    "callback_data": "status:update_task",
                },
                {"id": "status_refresh", "label": "Atualizar lista", "callback_data": "status:refresh"},
                {"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"},
            ]
        )
        return {
            "current_flow": "status",
            "current_step": "waiting_status_action",
            "task_selection_map": {str(i): task_id(task) for i, task in enumerate(visible_tasks, start=1) if task_id(task)},
            "final_message": "\n".join(lines),
            "response_ui": numbered_list(options, limit=self.settings.agent_max_ui_options),
            "response_status": "waiting_user_input",
            "response_data": {"tasks_count": len(visible_tasks)},
        }

    async def _show_task_detail(self, state: PMOAgentState, number: int) -> PMOAgentState:
        selection = await self.selections.resolve(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="status",
            selection_number=number,
        )
        if not selection:
            return {
                "current_flow": "status",
                "current_step": "selection_expired",
                "final_message": "Essa lista expirou. Vou buscar suas atividades novamente.",
                "response_ui": inline_keyboard(
                    [{"id": "status_refresh", "label": "Atualizar lista", "callback_data": "status:refresh"}]
                ),
                "response_status": "validation_error",
                "error_code": "TASK_SELECTION_EXPIRED",
            }
        task = await self.gateway.execute(
            tool_name="board_get_task",
            arguments={"id": selection["task_id"]},
            context=_context(state, intent="task.get"),
        )
        task_payload = task.result if isinstance(task.result, dict) else {"id": selection["task_id"], "raw": task.result}
        message = _task_detail_message(task_payload)
        return {
            "current_flow": "status",
            "current_step": "showing_task_detail",
            "selected_task_id": selection["task_id"],
            "selected_task_number": number,
            "board_result": task_payload,
            "final_message": message,
            "response_ui": inline_keyboard(
                [
                    {
                        "id": "status_update_task",
                        "label": "Atualizar atividade",
                        "callback_data": "status:update_task",
                    },
                    {"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"},
                ]
            ),
            "response_status": "waiting_user_input",
            "response_data": {"task": task_payload},
        }


def _context(state: PMOAgentState, *, intent: str) -> ToolExecutionContext:
    return ToolExecutionContext(
        request_id=state["request_id"],
        correlation_id=state["correlation_id"],
        thread_id=state["thread_id"],
        tenant_id=state["tenant_id"],
        user_id=state["user_id"],
        user_roles=state.get("user_roles") or [],
        intent=intent,
        approval_status="not_required",
    )


def _today(state: PMOAgentState):
    timezone = (state.get("metadata") or {}).get("timezone") or "America/Sao_Paulo"
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except Exception:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _selected_number(state: PMOAgentState) -> int | None:
    callback = state.get("callback_data") or ""
    if callback.startswith("status:task:"):
        return first_int(callback)
    if state.get("message_type") == "task_selection":
        return first_int(state.get("message_text"))
    text = (state.get("message_text") or "").strip()
    if text.isdigit() and state.get("current_flow") == "status":
        return int(text)
    return None


def _combine_tasks(my_tasks: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for task in my_tasks + blockers:
        ident = task_id(task)
        if not ident:
            continue
        merged = {**combined.get(ident, {}), **task}
        if task in blockers:
            merged["_from_blockers"] = True
        combined[ident] = merged
    return list(combined.values())


def _categorize_tasks(tasks: list[dict[str, Any]], today) -> dict[str, list[dict[str, Any]]]:
    categories = {"blocked": [], "overdue": [], "today": []}
    for task in tasks:
        due = parse_iso_date(task_due_date(task))
        status = str(task.get("status") or "").upper()
        if task.get("_from_blockers") or task.get("blocked") or status == "BLOCKED":
            categories["blocked"].append(task)
        elif due and due < today:
            categories["overdue"].append(task)
        elif due and due == today:
            categories["today"].append(task)
    for key in categories:
        categories[key].sort(key=lambda item: (task_priority(item), task_due_date(item) or "9999-12-31", task_title(item)))
    return categories


def _task_detail_message(task: dict[str, Any]) -> str:
    title = task_title(task)
    due = format_date_br(task_due_date(task))
    status = task.get("status") or "nao informado"
    assignee = task.get("assignee") or task.get("assignee_name") or task.get("owner") or "nao informado"
    return (
        f"Resumo da atividade\n\n"
        f"Tarefa: {title}\n"
        f"ID: {task_id(task) or 'nao informado'}\n"
        f"Status: {status}\n"
        f"Vencimento: {due}\n"
        f"Responsavel: {assignee}"
    )

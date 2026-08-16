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
    new_ui_context_id,
    normalize_task_payload,
    parse_iso_date,
    status_label,
    task_assignee_name,
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
        if callback == "status:refresh":
            return await self._show_status_list(state)
        number = _selected_number(state)
        selected_task_id = _selected_task_id(state)
        if callback == "status:update_task":
            if state.get("selected_task_id"):
                return await self._ask_update_selected_task(state, state["selected_task_id"])
            return self._ask_task_to_update()
        if selected_task_id:
            return await self._show_task_detail_by_id(state, selected_task_id, number)
        if number is not None:
            return await self._handle_number_selection(state, number)
        return await self._show_status_list(state)

    async def _show_status_list(self, state: PMOAgentState, *, notice: str | None = None) -> PMOAgentState:
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
        ui_context_id = new_ui_context_id("status")
        selection_map = await self.selections.replace_map(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="status",
            tasks=visible_tasks,
            ui_context_id=ui_context_id,
        )

        if not visible_tasks:
            lines = []
            if notice:
                lines.extend([notice, ""])
            lines.append("Voc\u00ea n\u00e3o possui atividades atrasadas, bloqueadas ou previstas para hoje. \u2705")
            return {
                "current_flow": "status",
                "current_step": "waiting_status_action",
                "task_selection_map": {},
                "last_ui_context_id": ui_context_id,
                "final_message": "\n".join(lines),
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Menu", "callback_data": "global:menu", "row": 1}],
                    context_id=ui_context_id,
                ),
                "response_status": "waiting_user_input",
                "response_data": {"tasks": []},
            }

        lines = []
        if notice:
            lines.extend([notice, ""])
        lines.extend(
            [
                "\U0001f4ca Seu status de atividades",
                (
                    f"{len(categorized['blocked'])} bloqueada(s), "
                    f"{len(categorized['overdue'])} atrasada(s), "
                    f"{len(categorized['today'])} para hoje."
                ),
            ]
        )
        options: list[dict[str, Any]] = []
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
                assignee = task_assignee_name(task)
                lines.append(f"{index}. {title_text} | vencimento {due} | respons\u00e1vel {assignee}")
                ident = task_id(task)
                options.append(
                    {
                        "id": f"status_task_{index}",
                        "label": f"Ver {index}",
                        "callback_data": f"status:id:{ident}" if ident else f"status:task:{index}",
                        "row": index,
                    }
                )
                index += 1
        options.extend(
            [
                {"id": "status_refresh", "label": "Atualizar lista", "callback_data": "status:refresh", "row": index},
                {"id": "global_menu", "label": "Menu", "callback_data": "global:menu", "row": index},
            ]
        )
        return {
            "current_flow": "status",
            "current_step": "waiting_status_action",
            "task_selection_map": selection_map,
            "last_ui_context_id": ui_context_id,
            "final_message": "\n".join(lines),
            "response_ui": inline_keyboard(
                options,
                limit=self.settings.agent_max_ui_options,
                context_id=ui_context_id,
            ),
            "response_status": "waiting_user_input",
            "response_data": {"tasks_count": len(visible_tasks)},
        }

    async def _handle_number_selection(self, state: PMOAgentState, number: int) -> PMOAgentState:
        ui_context_id = _inbound_ui_context_id(state)
        resolved = await self.selections.resolve_with_status(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="status",
            selection_number=number,
            ui_context_id=ui_context_id,
        )
        if resolved["status"] == "ok" and resolved.get("selection"):
            return await self._show_task_detail_by_id(state, resolved["selection"]["task_id"], number)

        legacy_action = _legacy_number_action(state, number)
        if legacy_action == "update":
            return self._ask_task_to_update()
        if legacy_action == "refresh":
            return await self._show_status_list(state)
        if legacy_action == "menu":
            return {
                "current_flow": "main_menu",
                "current_step": "waiting_menu_selection",
                "final_message": "O que voc\u00ea deseja fazer?",
                "response_ui": inline_keyboard(
                    [
                        {"id": "menu_status", "label": "\U0001f4ca Status", "callback_data": "menu:status"},
                        {"id": "menu_create", "label": "\u2795 Criar atividade", "callback_data": "menu:create"},
                        {"id": "menu_update", "label": "\u270f\ufe0f Atualizar atividade", "callback_data": "menu:update"},
                    ]
                ),
                "response_status": "waiting_user_input",
            }

        if resolved["status"] == "expired":
            return await self._show_status_list(
                state,
                notice="A lista anterior expirou. Atualizei suas atividades para voc\u00ea escolher de novo.",
            )

        return {
            "current_flow": "status",
            "current_step": "invalid_status_selection",
            "final_message": "N\u00e3o encontrei essa op\u00e7\u00e3o na lista atual. Escolha um dos bot\u00f5es ou envie o n\u00famero de uma tarefa.",
            "response_ui": inline_keyboard(
                [
                    {"id": "status_refresh", "label": "Atualizar lista", "callback_data": "status:refresh"},
                    {"id": "global_menu", "label": "Menu", "callback_data": "global:menu"},
                ]
            ),
            "response_status": "validation_error",
            "error_code": "TASK_SELECTION_NOT_FOUND",
        }

    async def _show_task_detail_by_id(
        self,
        state: PMOAgentState,
        selected_task_id: str,
        number: int | None = None,
    ) -> PMOAgentState:
        if not selected_task_id:
            return {
                "current_flow": "status",
                "current_step": "invalid_status_selection",
                "final_message": "N\u00e3o encontrei essa atividade. Atualize a lista e tente novamente.",
                "response_ui": inline_keyboard(
                    [{"id": "status_refresh", "label": "Atualizar lista", "callback_data": "status:refresh"}]
                ),
                "response_status": "validation_error",
                "error_code": "TASK_SELECTION_NOT_FOUND",
            }
        task = await self.gateway.execute(
            tool_name="board_get_task",
            arguments={"id": selected_task_id},
            context=_context(state, intent="task.get"),
        )
        task_payload = normalize_task_payload(task.result, fallback_id=selected_task_id)
        message = _task_detail_message(task_payload)
        return {
            "current_flow": "status",
            "current_step": "showing_task_detail",
            "selected_task_id": selected_task_id,
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
                    {"id": "global_menu", "label": "Menu", "callback_data": "global:menu"},
                ]
            ),
            "response_status": "waiting_user_input",
            "response_data": {"task": task_payload},
        }

    async def _ask_update_selected_task(self, state: PMOAgentState, selected_task_id: str) -> PMOAgentState:
        return {
            "current_flow": "task_update",
            "current_step": "waiting_update_fields",
            "selected_task_id": selected_task_id,
            "final_message": "O que voc\u00ea deseja atualizar nessa atividade?\n\nVoc\u00ea pode alterar a data, o respons\u00e1vel ou adicionar um coment\u00e1rio.",
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Menu", "callback_data": "global:menu"}]
            ),
            "response_status": "waiting_user_input",
        }

    def _ask_task_to_update(self) -> PMOAgentState:
        return {
            "current_flow": "task_update",
            "current_step": "waiting_task_selection",
            "selected_task_id": None,
            "final_message": "Qual atividade voc\u00ea deseja atualizar?",
            "response_ui": inline_keyboard(
                [
                    {"id": "update_list_tasks", "label": "Ver minhas atividades", "callback_data": "update:list_tasks"},
                    {"id": "global_menu", "label": "Menu", "callback_data": "global:menu"},
                ]
            ),
            "response_status": "waiting_user_input",
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


def _selected_task_id(state: PMOAgentState) -> str | None:
    callback = state.get("callback_data") or ""
    if not callback.startswith("status:id:"):
        return None
    value = callback.removeprefix("status:id:").strip()
    return value or None


def _inbound_ui_context_id(state: PMOAgentState) -> str | None:
    metadata = state.get("metadata") or {}
    extra = metadata.get("extra") or {}
    if isinstance(extra, dict):
        value = extra.get("ui_context_id") or state.get("last_ui_context_id")
        return str(value) if value else None
    value = state.get("last_ui_context_id")
    return str(value) if value else None


def _legacy_number_action(state: PMOAgentState, number: int) -> str | None:
    selection_map = state.get("task_selection_map") or {}
    if not selection_map:
        return None
    task_count = len(selection_map)
    legacy_actions = {
        task_count + 1: "update",
        task_count + 2: "refresh",
        task_count + 3: "menu",
    }
    return legacy_actions.get(number)


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
    status = status_label(task.get("status"))
    assignee = task_assignee_name(task)
    return (
        f"Resumo da atividade\n\n"
        f"Tarefa: {title}\n"
        f"ID: {task_id(task) or 'N\u00e3o informado'}\n"
        f"Status: {status}\n"
        f"Vencimento: {due}\n"
        f"Respons\u00e1vel: {assignee}"
    )

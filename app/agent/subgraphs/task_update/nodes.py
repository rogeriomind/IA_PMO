from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.agent.context import ToolExecutionContext
from app.agent.errors import AgentError
from app.agent.extraction.extractor import TaskExtractionService
from app.agent.main_graph.state import PMOAgentState
from app.agent.mcp_gateway import MCPGateway
from app.agent.subgraphs.common import (
    confirmation_ui,
    extract_tasks,
    first_int,
    format_date_br,
    inline_keyboard,
    looks_like_task_code,
    numbered_list,
    normalize_task_payload,
    task_assignee_name,
    task_due_date,
    task_id,
    task_title,
)
from app.application.assignee_resolver import AssigneeResolver
from app.application.draft_service import DraftService
from app.application.task_selection_service import TaskSelectionService
from app.config import Settings
from app.storage.repository import PendingActionRepository, utcnow


class UpdateTaskSubgraph:
    def __init__(
        self,
        *,
        gateway: MCPGateway,
        extractor: TaskExtractionService,
        selections: TaskSelectionService,
        drafts: DraftService,
        assignees: AssigneeResolver,
        repository: PendingActionRepository,
        settings: Settings,
    ):
        self.gateway = gateway
        self.extractor = extractor
        self.selections = selections
        self.drafts = drafts
        self.assignees = assignees
        self.repository = repository
        self.settings = settings

    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        callback = state.get("callback_data") or ""
        text = (state.get("message_text") or "").strip()

        if callback == "update:list_tasks":
            return await self._list_tasks(state)
        if callback.startswith("update:page:"):
            return await self._list_tasks(state, page=first_int(callback) or 1)
        if callback == "update:enter_task_id":
            return {
                "current_flow": "task_update",
                "current_step": "waiting_task_selection",
                "final_message": "Envie o n\u00famero ou c\u00f3digo real da atividade.",
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "waiting_user_input",
            }
        if callback.startswith("update:task:"):
            number = first_int(callback)
            if number is not None:
                return await self._select_by_number(state, number)

        selected_task_id = state.get("selected_task_id")
        if selected_task_id and not text:
            return await self._ask_update_fields(state, selected_task_id)

        if not selected_task_id:
            if text:
                selected = await self._resolve_task_from_text(state, text)
                if selected.get("selected_task_id"):
                    selected_task_id = selected["selected_task_id"]
                    if selected.get("current_step") == "waiting_update_fields":
                        return selected
                else:
                    return selected
            else:
                return self._ask_task_selection()

        if not text:
            return await self._ask_update_fields(state, selected_task_id)
        return await self._preview_and_confirm(state, selected_task_id, text)

    def _ask_task_selection(self) -> PMOAgentState:
        return {
            "current_flow": "task_update",
            "current_step": "waiting_task_selection",
            "selected_task_id": None,
            "final_message": (
                "Qual atividade voc\u00ea deseja atualizar?\n\n"
                "Voc\u00ea pode informar o n\u00famero ou c\u00f3digo da tarefa, ou visualizar suas atividades."
            ),
            "response_ui": inline_keyboard(
                [
                    {"id": "update_list_tasks", "label": "Ver minhas atividades", "callback_data": "update:list_tasks"},
                    {
                        "id": "update_enter_task_id",
                        "label": "Informar n\u00famero da tarefa",
                        "callback_data": "update:enter_task_id",
                    },
                    {"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"},
                ]
            ),
            "response_status": "waiting_user_input",
        }

    async def _list_tasks(self, state: PMOAgentState, *, page: int = 1) -> PMOAgentState:
        project_id = (state.get("metadata") or {}).get("project_id")
        try:
            result = await self.gateway.execute(
                tool_name="board_list_my_tasks",
                arguments={"user_id": state["user_id"], "project_id": project_id},
                context=_context(state, intent="user.my_tasks"),
            )
        except AgentError as exc:
            return {
                "current_flow": "task_update",
                "current_step": "update_list_error",
                "final_message": exc.user_message,
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "degraded",
                "error_code": exc.code,
            }
        tasks = extract_tasks(result.result)
        await self.selections.replace_map(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="update",
            tasks=tasks,
        )
        if not tasks:
            return {
                "current_flow": "task_update",
                "current_step": "waiting_task_selection",
                "final_message": "N\u00e3o encontrei atividades para atualizar.",
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "not_found",
            }
        page_size = self.settings.agent_update_page_size
        start = max(0, (page - 1) * page_size)
        page_tasks = tasks[start : start + page_size]
        lines = ["Escolha uma atividade:"]
        options: list[dict[str, str]] = []
        for absolute_index, task in enumerate(page_tasks, start=start + 1):
            title = task_title(task)
            lines.append(f"{absolute_index}. {title}")
            options.append(
                {
                    "id": f"update_task_{absolute_index}",
                    "label": f"{absolute_index}. {title}",
                    "callback_data": f"update:task:{absolute_index}",
                }
            )
        if start + page_size < len(tasks):
            options.append(
                {
                    "id": f"update_page_{page + 1}",
                    "label": "Proxima pagina",
                    "callback_data": f"update:page:{page + 1}",
                }
            )
        options.append({"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"})
        return {
            "current_flow": "task_update",
            "current_step": "waiting_task_selection",
            "final_message": "\n".join(lines),
            "response_ui": numbered_list(options, limit=self.settings.agent_max_ui_options),
            "response_status": "waiting_user_input",
            "response_data": {"tasks_count": len(tasks), "page": page},
        }

    async def _resolve_task_from_text(self, state: PMOAgentState, text: str) -> PMOAgentState:
        if text.isdigit():
            selection = await self.selections.resolve(
                tenant_id=state["tenant_id"],
                thread_id=state["thread_id"],
                user_id=state["user_id"],
                context="update",
                selection_number=int(text),
            )
            if selection:
                return await self._select_task_id(state, selection["task_id"])
        if looks_like_task_code(text):
            return await self._select_task_id(state, text.strip())
        return await self._search_task(state, text)

    async def _select_by_number(self, state: PMOAgentState, number: int) -> PMOAgentState:
        selection = await self.selections.resolve(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="update",
            selection_number=number,
        )
        if not selection:
            return {
                "current_flow": "task_update",
                "current_step": "waiting_task_selection",
                "final_message": "Essa lista expirou ou o n\u00famero n\u00e3o existe. Pe\u00e7a para ver suas atividades novamente.",
                "response_ui": inline_keyboard(
                    [{"id": "update_list_tasks", "label": "Ver minhas atividades", "callback_data": "update:list_tasks"}]
                ),
                "response_status": "validation_error",
                "error_code": "TASK_SELECTION_EXPIRED",
            }
        return await self._select_task_id(state, selection["task_id"])

    async def _search_task(self, state: PMOAgentState, query: str) -> PMOAgentState:
        result = await self.gateway.execute(
            tool_name="board_search_tasks",
            arguments={"search": query, "project_id": (state.get("metadata") or {}).get("project_id")},
            context=_context(state, intent="task.search"),
        )
        tasks = extract_tasks(result.result)
        if not tasks:
            return {
                "current_flow": "task_update",
                "current_step": "waiting_task_selection",
                "final_message": "N\u00e3o encontrei uma atividade com essa refer\u00eancia.",
                "response_ui": inline_keyboard(
                    [{"id": "update_list_tasks", "label": "Ver minhas atividades", "callback_data": "update:list_tasks"}]
                ),
                "response_status": "not_found",
            }
        if len(tasks) == 1:
            return await self._select_task_id(state, task_id(tasks[0]) or query)
        await self.selections.replace_map(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            context="update",
            tasks=tasks,
        )
        options = [
            {
                "id": f"update_task_{index}",
                "label": f"{index}. {task_title(task)}",
                "callback_data": f"update:task:{index}",
            }
            for index, task in enumerate(tasks[: self.settings.agent_update_page_size], start=1)
        ]
        return {
            "current_flow": "task_update",
            "current_step": "waiting_task_selection",
            "final_message": "Encontrei mais de uma atividade. Escolha uma op\u00e7\u00e3o para evitar atualiza\u00e7\u00e3o amb\u00edgua.",
            "response_ui": numbered_list(options, limit=self.settings.agent_max_ui_options),
            "response_status": "waiting_user_input",
        }

    async def _select_task_id(self, state: PMOAgentState, selected_task_id: str) -> PMOAgentState:
        task = await self.gateway.execute(
            tool_name="board_get_task",
            arguments={"id": selected_task_id},
            context=_context(state, intent="task.get"),
        )
        task_payload = normalize_task_payload(task.result, fallback_id=selected_task_id)
        await self.drafts.save(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type="task_update",
            payload={"selected_task_id": selected_task_id, "current_task": task_payload},
        )
        return {
            "current_flow": "task_update",
            "current_step": "waiting_update_fields",
            "selected_task_id": selected_task_id,
            "board_result": task_payload,
            "final_message": (
                f"O que voc\u00ea deseja atualizar na atividade \"{task_title(task_payload)}\"?\n\n"
                "Voc\u00ea pode alterar a data, o respons\u00e1vel ou adicionar um coment\u00e1rio."
            ),
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
            ),
            "response_status": "waiting_user_input",
        }

    async def _ask_update_fields(self, state: PMOAgentState, selected_task_id: str) -> PMOAgentState:
        draft_record = await self.drafts.get(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type="task_update",
        )
        current_task = (draft_record or {}).get("payload", {}).get("current_task") or {"id": selected_task_id}
        return {
            "current_flow": "task_update",
            "current_step": "waiting_update_fields",
            "selected_task_id": selected_task_id,
            "final_message": (
                f"O que voc\u00ea deseja atualizar na atividade \"{task_title(current_task)}\"?\n\n"
                "Voc\u00ea pode alterar a data, o respons\u00e1vel ou adicionar um coment\u00e1rio."
            ),
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
            ),
            "response_status": "waiting_user_input",
        }

    async def _preview_and_confirm(
        self,
        state: PMOAgentState,
        selected_task_id: str,
        text: str,
    ) -> PMOAgentState:
        extraction = await self.extractor.extract_update(
            text,
            timezone=(state.get("metadata") or {}).get("timezone") or "America/Sao_Paulo",
            trace=state.get("_trace"),
        )
        fields = dict(extraction.fields or {})
        comment = extraction.comment
        unresolved_assignee_message = None
        if extraction.assignee_name:
            resolution = await self.assignees.resolve(
                assignee_name=extraction.assignee_name,
                current_user_id=state["user_id"],
                current_user_name=state.get("user_name"),
            )
            if resolution.status == "resolved" and resolution.assignee_id:
                fields["assignee_id"] = resolution.assignee_id
            else:
                fields.pop("assignee", None)
                unresolved_assignee_message = (
                    "N\u00e3o h\u00e1 uma resolu\u00e7\u00e3o segura para esse respons\u00e1vel neste ambiente."
                )

        allowed_fields = {key: value for key, value in fields.items() if key in {"due_date", "assignee_id"} and value}
        if not allowed_fields and not comment:
            return {
                "current_flow": "task_update",
                "current_step": "waiting_update_fields",
                "selected_task_id": selected_task_id,
                "final_message": (
                    unresolved_assignee_message
                    or "O que voc\u00ea deseja alterar? Posso atualizar data, respons\u00e1vel ou adicionar coment\u00e1rio."
                ),
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "waiting_user_input",
                "error_code": "NO_SUPPORTED_UPDATE_FIELDS",
            }

        current_task = await self._load_current_task(state, selected_task_id)
        operations: list[dict[str, Any]] = []
        if allowed_fields:
            operations.append(
                {
                    "tool_name": "board_update_task",
                    "intent": "task.update",
                    "arguments": {"task_id": selected_task_id, "fields": allowed_fields},
                }
            )
        if comment:
            operations.append(
                {
                    "tool_name": "board_add_comment",
                    "intent": "task.comment",
                    "arguments": {"task_id": selected_task_id, "comment": comment},
                }
            )
        preview = {
            "task_id": selected_task_id,
            "task_title": task_title(current_task),
            "current_task": current_task,
            "fields": allowed_fields,
            "comment": comment,
            "unresolved_assignee": unresolved_assignee_message,
        }
        pending = self.repository.create_v2_pending_action(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            request_id=state["request_id"],
            correlation_id=state["correlation_id"],
            action_type="task.update",
            tool_name="multiple" if len(operations) > 1 else operations[0]["tool_name"],
            operations=operations,
            payload={"task_id": selected_task_id, "fields": allowed_fields, "comment": comment},
            preview=preview,
            expires_at=utcnow() + timedelta(minutes=self.settings.agent_pending_action_ttl_minutes),
        )
        await self.drafts.save(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type="task_update",
            payload={"selected_task_id": selected_task_id, "current_task": current_task, "preview": preview},
        )
        message = _preview_message(preview)
        return {
            "current_flow": "confirmation",
            "current_step": "awaiting_confirmation",
            "previous_flow": "task_update",
            "previous_step": "waiting_update_fields",
            "selected_task_id": selected_task_id,
            "update_draft": preview,
            "pending_action_id": pending["id"],
            "proposed_operations": operations,
            "final_message": message,
            "response_ui": confirmation_ui(pending["id"]),
            "response_status": "awaiting_confirmation",
            "requires_confirmation": True,
            "confirmation": {
                "id": pending["id"],
                "action_type": "task.update",
                "preview": preview,
                "expires_at": pending.get("expires_at"),
            },
            "response_data": {"pending_action_id": pending["id"], "operations_count": len(operations)},
        }

    async def _load_current_task(self, state: PMOAgentState, selected_task_id: str) -> dict[str, Any]:
        try:
            task = await self.gateway.execute(
                tool_name="board_get_task",
                arguments={"id": selected_task_id},
                context=_context(state, intent="task.get"),
            )
            return normalize_task_payload(task.result, fallback_id=selected_task_id)
        except Exception:
            pass
        return {"id": selected_task_id}


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


def _preview_message(preview: dict[str, Any]) -> str:
    task = preview.get("current_task") or {}
    fields = preview.get("fields") or {}
    lines = [f"Vou atualizar a atividade \"{preview.get('task_title')}\":", ""]
    if "due_date" in fields:
        lines.append(f"Data atual: {format_date_br(task_due_date(task))}")
        lines.append(f"Nova data: {format_date_br(fields['due_date'])}")
    if "assignee_id" in fields:
        current_assignee = task_assignee_name(task)
        lines.append(f"Responsavel atual: {current_assignee}")
        lines.append(f"Novo responsavel: {fields['assignee_id']}")
    if preview.get("comment"):
        lines.append(f"Coment\u00e1rio: {preview['comment']}")
    if preview.get("unresolved_assignee"):
        lines.extend(["", preview["unresolved_assignee"], "Essa parte n\u00e3o ser\u00e1 executada."])
    lines.extend(["", "Confirma a atualiza\u00e7\u00e3o?"])
    return "\n".join(lines)

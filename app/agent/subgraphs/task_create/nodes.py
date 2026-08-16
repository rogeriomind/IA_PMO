from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.agent.extraction.extractor import TaskExtractionService
from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import confirmation_ui, format_date_br, inline_keyboard, priority_label
from app.application.assignee_resolver import AssigneeResolution, AssigneeResolver
from app.application.draft_service import DraftService
from app.config import Settings
from app.storage.repository import PendingActionRepository, utcnow


class CreateTaskSubgraph:
    def __init__(
        self,
        *,
        extractor: TaskExtractionService,
        drafts: DraftService,
        assignees: AssigneeResolver,
        repository: PendingActionRepository,
        settings: Settings,
    ):
        self.extractor = extractor
        self.drafts = drafts
        self.assignees = assignees
        self.repository = repository
        self.settings = settings

    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        callback = state.get("callback_data") or ""
        text = (state.get("message_text") or "").strip()

        draft_record = await self.drafts.get(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type="task_create",
        )
        draft = dict((draft_record or {}).get("payload") or state.get("create_draft") or {})
        step = state.get("current_step")

        if callback.startswith("create:assignee:"):
            return await self._select_assignee(state, draft, callback.removeprefix("create:assignee:"))
        if callback == "create:skip_assignee":
            for key in ("assignee_id", "assignee_name", "assignee_email", "assignee_options"):
                draft.pop(key, None)
            await self._save_draft(state, draft)
            return await self._preview_and_confirm(state, draft)

        if not text:
            return await self._ask_initial(state)

        if step == "waiting_create_title" and not _looks_like_date_only(text):
            draft["title"] = text
        elif step == "waiting_create_due_date":
            extracted_date = await self.extractor.extract_date(
                text,
                timezone=(state.get("metadata") or {}).get("timezone") or "America/Sao_Paulo",
            )
            if extracted_date.due_date:
                draft["due_date"] = extracted_date.due_date
            else:
                draft["due_date_text"] = text
        elif step == "waiting_create_assignee_selection":
            draft["assignee_name"] = text
            draft.pop("assignee_id", None)
            draft.pop("assignee_email", None)
            draft.pop("assignee_options", None)
        else:
            extraction = await self.extractor.extract_create(
                text,
                timezone=(state.get("metadata") or {}).get("timezone") or "America/Sao_Paulo",
                trace=state.get("_trace"),
            )
            draft = _merge_draft(draft, extraction.model_dump(exclude_none=True))

        project_id = (state.get("metadata") or {}).get("project_id") or draft.get("project_id")
        if project_id:
            draft["project_id"] = project_id

        if not draft.get("title"):
            await self._save_draft(state, draft)
            return {
                "current_flow": "task_create",
                "current_step": "waiting_create_title",
                "create_draft": draft,
                "final_message": "Qual deve ser o t\u00edtulo da atividade?",
                "response_ui": inline_keyboard(
                    [{"id": "global_cancel", "label": "Cancelar", "callback_data": "global:cancel"}]
                ),
                "response_status": "waiting_user_input",
            }
        if not draft.get("due_date"):
            await self._save_draft(state, draft)
            return {
                "current_flow": "task_create",
                "current_step": "waiting_create_due_date",
                "create_draft": draft,
                "final_message": "Qual \u00e9 a data de entrega?",
                "response_ui": inline_keyboard(
                    [{"id": "global_cancel", "label": "Cancelar", "callback_data": "global:cancel"}]
                ),
                "response_status": "waiting_user_input",
            }

        return await self._preview_and_confirm(state, draft)

    async def _ask_initial(self, state: PMOAgentState) -> PMOAgentState:
        return {
            "current_flow": "task_create",
            "current_step": "waiting_create_details",
            "create_draft": {},
            "final_message": (
                "Certo. Me diga o t\u00edtulo da atividade e a data de entrega.\n\n"
                "Voc\u00ea tamb\u00e9m pode informar respons\u00e1vel, prioridade e uma observa\u00e7\u00e3o na mesma mensagem."
            ),
            "response_ui": inline_keyboard(
                [
                    {
                        "id": "create_without_optional",
                        "label": "Continuar sem observa\u00e7\u00e3o e respons\u00e1vel",
                        "callback_data": "create:skip_optional",
                    },
                    {"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"},
                ]
            ),
            "response_status": "waiting_user_input",
        }

    async def _preview_and_confirm(self, state: PMOAgentState, draft: dict[str, Any]) -> PMOAgentState:
        if draft.get("assignee_id"):
            assignee_resolution = AssigneeResolution(
                status="resolved",
                assignee_id=draft.get("assignee_id"),
                display_name=draft.get("assignee_name"),
                email=draft.get("assignee_email"),
            )
        else:
            assignee_resolution = await self.assignees.resolve(
                assignee_name=draft.get("assignee_name"),
                tenant_id=state["tenant_id"],
                channel=state["channel"],
                provider_user_id=state["user_id"],
                current_user_id=state["user_id"],
                current_user_name=state.get("user_name"),
                current_username=state.get("username"),
            )
        if assignee_resolution.status in {"needs_selection", "unavailable"} and draft.get("assignee_name"):
            draft["assignee_options"] = assignee_resolution.options or []
            await self._save_draft(state, draft)
            return _ask_assignee_selection(draft, assignee_resolution)

        payload = {
            "title": draft["title"],
            "due_date": draft["due_date"],
            "description": draft.get("description"),
            "priority": draft.get("priority"),
            "project_id": draft.get("project_id"),
        }
        if assignee_resolution.status == "resolved" and assignee_resolution.assignee_id:
            payload["assigneeId"] = assignee_resolution.assignee_id

        payload = {key: value for key, value in payload.items() if value not in (None, "", {}, [])}
        preview = {
            "title": draft["title"],
            "due_date": draft["due_date"],
            "assignee_name": assignee_resolution.display_name or draft.get("assignee_name"),
            "assignee_id": assignee_resolution.assignee_id,
            "assignee_email": assignee_resolution.email,
            "assignee_status": assignee_resolution.status,
            "priority": draft.get("priority"),
            "description": draft.get("description"),
            "project_id": draft.get("project_id"),
        }
        operations = [
            {
                "tool_name": "board_create_task",
                "intent": "task.create",
                "arguments": payload,
            }
        ]
        pending = self.repository.create_v2_pending_action(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            request_id=state["request_id"],
            correlation_id=state["correlation_id"],
            action_type="task.create",
            tool_name="board_create_task",
            operations=operations,
            payload=payload,
            preview=preview,
            expires_at=utcnow() + timedelta(minutes=self.settings.agent_pending_action_ttl_minutes),
        )
        await self._save_draft(state, draft)
        message = _preview_message(preview)
        return {
            "current_flow": "confirmation",
            "current_step": "awaiting_confirmation",
            "previous_flow": "task_create",
            "previous_step": state.get("current_step"),
            "create_draft": draft,
            "pending_action_id": pending["id"],
            "proposed_operations": operations,
            "final_message": message,
            "response_ui": confirmation_ui(pending["id"]),
            "response_status": "awaiting_confirmation",
            "requires_confirmation": True,
            "confirmation": {
                "id": pending["id"],
                "action_type": "task.create",
                "preview": preview,
                "expires_at": pending.get("expires_at"),
            },
            "response_data": {"pending_action_id": pending["id"]},
        }

    async def _select_assignee(
        self,
        state: PMOAgentState,
        draft: dict[str, Any],
        selected_user_id: str,
    ) -> PMOAgentState:
        user = _find_assignee_option(draft, selected_user_id)
        if not user:
            return {
                "current_flow": "task_create",
                "current_step": "waiting_create_assignee_selection",
                "create_draft": draft,
                "final_message": "Nao encontrei essa opcao de responsavel. Envie o nome ou e-mail novamente.",
                "response_ui": inline_keyboard(
                    [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
                ),
                "response_status": "validation_error",
                "error_code": "ASSIGNEE_SELECTION_NOT_FOUND",
            }
        self.assignees.link_if_current_user(
            tenant_id=state["tenant_id"],
            channel=state["channel"],
            provider_user_id=state["user_id"],
            user=user,
            current_user_name=state.get("user_name"),
            current_username=state.get("username"),
            source="explicit_assignee_selection",
        )
        draft["assignee_id"] = user["id"]
        draft["assignee_name"] = user.get("name") or user.get("email") or user["id"]
        draft["assignee_email"] = user.get("email")
        draft.pop("assignee_options", None)
        await self._save_draft(state, draft)
        return await self._preview_and_confirm(state, draft)

    async def _save_draft(self, state: PMOAgentState, draft: dict[str, Any]) -> None:
        await self.drafts.save(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type="task_create",
            payload=draft,
        )


def _merge_draft(draft: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    merged = dict(draft)
    for key, value in extracted.items():
        if value not in (None, "", {}, []):
            merged[key] = value
    return merged


def _looks_like_date_only(text: str) -> bool:
    return any(part in text.casefold() for part in ("hoje", "amanh", "segunda", "ter", "quarta", "quinta", "sexta")) or "/" in text


def _ask_assignee_selection(draft: dict[str, Any], resolution: AssigneeResolution) -> PMOAgentState:
    options = [
        {
            "id": f"create_assignee_{index}",
            "label": _assignee_label(user),
            "callback_data": f"create:assignee:{user['id']}",
            "row": index,
        }
        for index, user in enumerate(resolution.options or [], start=1)
        if user.get("id")
    ]
    row = len(options) + 1
    options.extend(
        [
            {
                "id": "create_skip_assignee",
                "label": "Continuar sem responsavel",
                "callback_data": "create:skip_assignee",
                "row": row,
            },
            {"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu", "row": row},
        ]
    )
    detail = (
        "Escolha uma das opcoes abaixo."
        if resolution.options
        else "Envie outro nome ou e-mail de usuario cadastrado no Board."
    )
    return {
        "current_flow": "task_create",
        "current_step": "waiting_create_assignee_selection",
        "create_draft": draft,
        "final_message": (
            f"Nao consegui vincular com seguranca o responsavel \"{draft.get('assignee_name')}\".\n\n{detail}"
        ),
        "response_ui": inline_keyboard(options),
        "response_status": "waiting_user_input",
        "response_data": {"assignee_options_count": len(resolution.options or [])},
    }


def _find_assignee_option(draft: dict[str, Any], selected_user_id: str) -> dict[str, str | None] | None:
    for user in draft.get("assignee_options") or []:
        if str(user.get("id")) == selected_user_id:
            return user
    return None


def _assignee_label(user: dict[str, str | None]) -> str:
    name = user.get("name") or "Usuario"
    email = user.get("email")
    return f"{name} ({email})" if email else name


def _preview_message(preview: dict[str, Any]) -> str:
    return (
        "Vou criar a atividade:\n\n"
        f"T\u00edtulo: {preview.get('title')}\n"
        f"Data: {format_date_br(preview.get('due_date'))}\n"
        f"Respons\u00e1vel: {preview.get('assignee_name') or 'Sem respons\u00e1vel'}\n"
        f"Prioridade: {priority_label(preview.get('priority'))}\n"
        f"Observa\u00e7\u00e3o: {preview.get('description') or 'Sem observa\u00e7\u00e3o'}\n\n"
        "Confirma a cria\u00e7\u00e3o?"
    )

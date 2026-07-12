from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.agent.extraction.extractor import TaskExtractionService
from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import confirmation_ui, format_date_br, inline_keyboard, priority_label
from app.application.assignee_resolver import AssigneeResolver
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
        text = (state.get("message_text") or "").strip()
        if not text:
            return await self._ask_initial(state)

        draft_record = await self.drafts.get(
            tenant_id=state["tenant_id"],
            thread_id=state["thread_id"],
            user_id=state["user_id"],
            draft_type="task_create",
        )
        draft = dict((draft_record or {}).get("payload") or state.get("create_draft") or {})
        step = state.get("current_step")

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
        assignee_resolution = await self.assignees.resolve(
            assignee_name=draft.get("assignee_name"),
            current_user_id=state["user_id"],
            current_user_name=state.get("user_name"),
        )
        payload = {
            "title": draft["title"],
            "due_date": draft["due_date"],
            "description": draft.get("description"),
            "priority": draft.get("priority"),
            "project_id": draft.get("project_id"),
        }
        if assignee_resolution.status == "resolved" and assignee_resolution.assignee_id:
            payload["assignee"] = assignee_resolution.assignee_id

        payload = {key: value for key, value in payload.items() if value not in (None, "", {}, [])}
        preview = {
            "title": draft["title"],
            "due_date": draft["due_date"],
            "assignee_name": assignee_resolution.display_name or draft.get("assignee_name"),
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
        if assignee_resolution.status == "unavailable" and draft.get("assignee_name"):
            message += (
                "\n\nN\u00e3o encontrei uma resolu\u00e7\u00e3o segura para esse respons\u00e1vel; "
                "a atividade ser\u00e1 criada sem respons\u00e1vel."
            )
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

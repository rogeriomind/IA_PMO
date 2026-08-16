from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime
from typing import Any
from uuid import uuid4


def ui_none() -> dict[str, Any]:
    return {"type": "none", "options": []}


def inline_keyboard(
    options: list[dict[str, Any]],
    *,
    limit: int = 12,
    context_id: str | None = None,
) -> dict[str, Any]:
    ui: dict[str, Any] = {"type": "inline_keyboard", "options": options[:limit]}
    if context_id:
        ui["context_id"] = context_id
    return ui


def numbered_list(
    options: list[dict[str, Any]],
    *,
    limit: int = 12,
    context_id: str | None = None,
) -> dict[str, Any]:
    ui: dict[str, Any] = {"type": "numbered_list", "options": options[:limit]}
    if context_id:
        ui["context_id"] = context_id
    return ui


def new_ui_context_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def confirmation_ui(confirmation_id: str) -> dict[str, Any]:
    return inline_keyboard(
        [
            {
                "id": "confirmation_approve",
                "label": "Confirmar",
                "callback_data": f"confirmation:approve:{confirmation_id}",
            },
            {
                "id": "confirmation_edit",
                "label": "Alterar informacoes",
                "callback_data": f"confirmation:edit:{confirmation_id}",
            },
            {
                "id": "confirmation_reject",
                "label": "Cancelar",
                "callback_data": f"confirmation:reject:{confirmation_id}",
            },
        ],
        limit=3,
    ) | {"type": "confirmation"}


def main_menu_options() -> list[dict[str, str]]:
    return [
        {"id": "menu_status", "label": "\U0001f4ca Status", "callback_data": "menu:status"},
        {"id": "menu_create", "label": "\u2795 Criar atividade", "callback_data": "menu:create"},
        {"id": "menu_update", "label": "\u270f\ufe0f Atualizar atividade", "callback_data": "menu:update"},
    ]


def task_id(task: dict[str, Any]) -> str | None:
    value = task.get("id") or task.get("task_id") or task.get("key") or task.get("uuid")
    return str(value) if value else None


def task_title(task: dict[str, Any]) -> str:
    return str(task.get("title") or task.get("name") or task_id(task) or "Atividade")


def task_due_date(task: dict[str, Any]) -> str | None:
    value = task.get("due_date") or task.get("dueDate") or task.get("due") or task.get("deadline")
    return str(value) if value else None


def task_priority(task: dict[str, Any]) -> int:
    value = str(task.get("priority") or "").upper()
    return {"CRITICAL": 0, "URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(value, 4)


def normalize_task_payload(result: Any, *, fallback_id: str | None = None) -> dict[str, Any]:
    task = _unwrap_task_payload(result)
    if not isinstance(task, dict):
        return _canonical_task({"id": fallback_id, "raw": task})
    return _canonical_task(task, fallback_id=fallback_id)


def normalize_tasks(result: Any) -> list[dict[str, Any]]:
    return [normalize_task_payload(item) for item in _extract_task_items(result)]


def extract_tasks(result: Any) -> list[dict[str, Any]]:
    return normalize_tasks(result)


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def format_date_br(value: str | None, today: date | None = None) -> str:
    parsed = parse_iso_date(value)
    if not parsed:
        return value or "sem data"
    if today and parsed == today:
        return "hoje"
    return parsed.strftime("%d/%m/%Y")


def priority_label(value: str | None) -> str:
    normalized = str(value or "").upper()
    return {
        "CRITICAL": "Cr\u00edtica",
        "URGENT": "Urgente",
        "HIGH": "Alta",
        "MEDIUM": "M\u00e9dia",
        "LOW": "Baixa",
    }.get(normalized, value or "N\u00e3o informada")


def status_label(value: str | None) -> str:
    normalized = str(value or "").upper()
    return {
        "TODO": "A fazer",
        "IN_PROGRESS": "Em andamento",
        "BLOCKED": "Bloqueada",
        "DONE": "Conclu\u00edda",
        "CANCELED": "Cancelada",
        "CANCELLED": "Cancelada",
    }.get(normalized, value or "N\u00e3o informado")


def task_assignee_name(task: dict[str, Any]) -> str:
    assignee = task.get("assignee")
    if isinstance(assignee, dict):
        value = assignee.get("name") or assignee.get("id")
        if value:
            return str(value)
        return "N\u00e3o informado"
    if assignee:
        return str(assignee)
    return str(task.get("assignee_name") or task.get("owner") or task.get("owner_name") or "N\u00e3o informado")


def looks_like_task_code(value: str) -> bool:
    return bool(re.fullmatch(r"\s*([A-Z]{1,12}-\d{1,12}|TASK-\d+|\d{3,})\s*", value.strip()))


def first_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{1,3})", value)
    return int(match.group(1)) if match else None


def _unwrap_task_payload(result: Any) -> Any:
    payload = deepcopy(result)
    while isinstance(payload, dict):
        if isinstance(payload.get("task"), dict):
            payload = payload["task"]
            continue
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("task"), dict):
            payload = data["task"]
            continue
        return payload
    return payload


def _extract_task_items(result: Any) -> list[Any]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if not isinstance(result, dict):
        return []

    for key in ("tasks", "items", "results"):
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    data = result.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("tasks", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if isinstance(data.get("task"), dict):
            return [data["task"]]

    task = result.get("task")
    if isinstance(task, dict):
        return [task]
    return []


def _canonical_task(task: dict[str, Any], *, fallback_id: str | None = None) -> dict[str, Any]:
    ident = task_id(task) or fallback_id
    assignee = _canonical_assignee(task)
    return {
        "id": str(ident) if ident else None,
        "title": str(task.get("title") or task.get("name") or task.get("summary") or ident or "Atividade"),
        "status": str(task.get("status") or task.get("state") or "") or None,
        "due_date": task_due_date(task),
        "priority": str(task.get("priority")) if task.get("priority") is not None else None,
        "assignee": assignee,
    }


def _canonical_assignee(task: dict[str, Any]) -> dict[str, str | None]:
    assignee = task.get("assignee") or task.get("assigned_to") or task.get("owner")
    if isinstance(assignee, dict):
        return {
            "id": _string_or_none(assignee.get("id") or assignee.get("user_id") or assignee.get("uuid")),
            "name": _string_or_none(assignee.get("name") or assignee.get("full_name") or assignee.get("username")),
        }
    return {
        "id": _string_or_none(task.get("assignee_id") or task.get("owner_id") or task.get("assigned_to_id")),
        "name": _string_or_none(
            task.get("assignee_name")
            or task.get("owner_name")
            or task.get("assigned_to_name")
            or (assignee if assignee else None)
        ),
    }


def _string_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)

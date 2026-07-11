from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


def ui_none() -> dict[str, Any]:
    return {"type": "none", "options": []}


def inline_keyboard(options: list[dict[str, str]], *, limit: int = 12) -> dict[str, Any]:
    return {"type": "inline_keyboard", "options": options[:limit]}


def numbered_list(options: list[dict[str, str]], *, limit: int = 12) -> dict[str, Any]:
    return {"type": "numbered_list", "options": options[:limit]}


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
        {"id": "menu_questions", "label": "\u2753 Duvidas", "callback_data": "menu:questions"},
    ]


def task_id(task: dict[str, Any]) -> str | None:
    value = task.get("id") or task.get("task_id") or task.get("key")
    return str(value) if value else None


def task_title(task: dict[str, Any]) -> str:
    return str(task.get("title") or task.get("name") or task_id(task) or "Atividade")


def task_due_date(task: dict[str, Any]) -> str | None:
    value = task.get("due_date") or task.get("dueDate") or task.get("due")
    return str(value) if value else None


def task_priority(task: dict[str, Any]) -> int:
    value = str(task.get("priority") or "").upper()
    return {"CRITICAL": 0, "URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(value, 4)


def extract_tasks(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        for key in ("tasks", "items", "data", "results"):
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        task = result.get("task")
        if isinstance(task, dict):
            return [task]
    return []


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
        "CRITICAL": "Critica",
        "HIGH": "Alta",
        "MEDIUM": "Media",
        "LOW": "Baixa",
    }.get(normalized, value or "Nao informada")


def looks_like_task_code(value: str) -> bool:
    return bool(re.fullmatch(r"\s*([A-Z]{1,12}-\d{1,12}|TASK-\d+|\d{3,})\s*", value.strip()))


def first_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{1,3})", value)
    return int(match.group(1)) if match else None

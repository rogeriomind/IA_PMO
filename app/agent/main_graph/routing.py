from __future__ import annotations

import re
import unicodedata

from app.agent.main_graph.state import PMOAgentState


GLOBAL_TEXT_COMMANDS = {
    "cancelar": "cancel",
    "cancela": "cancel",
    "voltar": "back",
    "menu": "menu",
    "inicio": "menu",
    "início": "menu",
    "reiniciar": "reset",
}

ISOLATED_GREETINGS = {
    "ola",
    "oi",
    "bom dia",
    "boa tarde",
    "boa noite",
}


def plain(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", (value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def global_command(state: PMOAgentState) -> str | None:
    callback = state.get("callback_data") or ""
    if callback == "global:cancel" or state.get("message_type") == "cancel":
        return "cancel"
    if callback == "global:back" or state.get("message_type") == "back":
        return "back"
    if callback == "global:menu":
        return "menu"
    if callback == "global:reset" or state.get("message_type") == "reset":
        return "reset"
    normalized = plain(state.get("message_text"))
    if normalized in ISOLATED_GREETINGS:
        return "menu"
    return GLOBAL_TEXT_COMMANDS.get(normalized)


def infer_menu_from_text(text: str | None) -> str | None:
    normalized = plain(text)
    if not normalized:
        return None
    if re.search(r"\b(status|minhas tarefas|meu trabalho|atividades de hoje|atrasadas|bloquead[ao]s?|bloqueios?)\b", normalized):
        return "status"
    if re.search(r"\b(criar|cria|nova atividade|nova tarefa|abrir atividade)\b", normalized):
        return "create"
    if re.search(r"\b(atualizar|atualiza|alterar|altere|editar|mudar)\b", normalized):
        return "update"
    if re.search(r"\b(duvida|duvidas|pergunta|ajuda)\b", normalized):
        return "questions"
    return None

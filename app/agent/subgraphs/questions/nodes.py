from __future__ import annotations

from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import inline_keyboard


class QuestionsSubgraph:
    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        return {
            "current_flow": "main_menu",
            "current_step": "waiting_menu_selection",
            "final_message": (
                "Posso ajudar agora com Status, Criar atividade e Atualizar atividade.\n\n"
                "Escolha uma op\u00e7\u00e3o abaixo para continuar."
            ),
            "response_ui": inline_keyboard(
                [
                    {"id": "menu_status", "label": "\U0001f4ca Status", "callback_data": "menu:status"},
                    {"id": "menu_create", "label": "\u2795 Criar atividade", "callback_data": "menu:create"},
                    {"id": "menu_update", "label": "\u270f\ufe0f Atualizar atividade", "callback_data": "menu:update"},
                ]
            ),
            "response_status": "waiting_user_input",
            "response_data": {},
        }

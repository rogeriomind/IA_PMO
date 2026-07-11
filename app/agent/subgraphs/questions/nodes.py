from __future__ import annotations

from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import inline_keyboard


class QuestionsSubgraph:
    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        return {
            "current_flow": "questions",
            "current_step": "mocked_questions",
            "final_message": (
                "A \u00e1rea de d\u00favidas ainda est\u00e1 em constru\u00e7\u00e3o.\n\n"
                "Em breve voc\u00ea poder\u00e1 consultar informa\u00e7\u00f5es sobre projetos, "
                "atividades, prazos e processos do PMO."
            ),
            "response_ui": inline_keyboard(
                [{"id": "global_menu", "label": "Voltar ao menu", "callback_data": "global:menu"}]
            ),
            "response_status": "waiting_user_input",
            "response_data": {},
        }

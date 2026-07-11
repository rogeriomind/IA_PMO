from __future__ import annotations

from app.agent.main_graph.state import PMOAgentState
from app.agent.subgraphs.common import inline_keyboard, main_menu_options


class WelcomeMenuSubgraph:
    async def handle(self, state: PMOAgentState) -> PMOAgentState:
        name = (state.get("user_name") or "").strip()
        greeting = f"Ol\u00e1, {name}! \U0001f44b" if name else "Ol\u00e1! \U0001f44b"
        return {
            "current_flow": "main_menu",
            "current_step": "waiting_menu_selection",
            "selected_menu": None,
            "final_message": f"{greeting}\n\nO que voc\u00ea deseja fazer?",
            "response_ui": inline_keyboard(main_menu_options()),
            "response_status": "waiting_user_input",
            "response_data": {},
            "requires_confirmation": False,
            "confirmation": None,
        }

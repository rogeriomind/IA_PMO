from __future__ import annotations

from typing import Any

from app.schemas import Intent


class ResponseService:
    def missing_fields_message(self, intent: Intent, missing_fields: list[str], entities: dict[str, Any]) -> str:
        if intent == Intent.TASK_CREATE and "title" in missing_fields:
            return "Qual e o titulo da tarefa que voce quer criar?"
        if "task" in missing_fields:
            return "Qual tarefa voce quer alterar? Pode me enviar o ID ou o titulo."
        if "status" in missing_fields:
            return "Para qual status voce quer mover essa tarefa?"
        if "comment" in missing_fields:
            return "Qual comentario voce quer adicionar na tarefa?"
        if "fields" in missing_fields:
            return "O que voce quer atualizar nessa tarefa?"
        if "task_ambiguity" in missing_fields:
            return "Encontrei mais de uma tarefa possivel. Envie o ID da tarefa que voce quer alterar."
        return "Preciso de mais um detalhe para continuar com essa acao."

    def confirmation_message(self, action: dict[str, Any]) -> str:
        action_type = action.get("type")
        payload = action.get("payload") or {}

        if action_type == "create_task":
            lines = ["Posso criar a tarefa abaixo?"]
            lines.extend(self._format_payload_lines(payload, ("title", "description", "assignee", "priority", "due_date", "project", "status")))
            lines.append("Confirma?")
            return "\n".join(lines)

        if action_type == "update_task":
            target = payload.get("task_id") or payload.get("task_query")
            return f"Posso atualizar a tarefa {target} com estes dados: {payload.get('fields', {})}? Confirma?"

        if action_type == "move_task":
            target = payload.get("task_id") or payload.get("task_query")
            return f"Posso mover a tarefa {target} para {payload.get('status')}? Confirma?"

        if action_type == "add_comment":
            target = payload.get("task_id") or payload.get("task_query")
            return f"Posso adicionar este comentario na tarefa {target}: {payload.get('comment')}? Confirma?"

        return "Posso executar essa acao no board? Confirma?"

    def read_response(self, intent: Intent, board_context: Any) -> str:
        if board_context is None:
            return "Nao consegui consultar dados suficientes do board agora."

        if intent == Intent.STATUS_BOARD:
            return self._status_board_response(board_context)

        if isinstance(board_context, str):
            return board_context

        return f"Consultei o board e encontrei: {board_context}"

    @staticmethod
    def smalltalk_response() -> str:
        return "Oi! Posso ajudar com status do projeto, criacao ou atualizacao de tarefas e duvidas sobre o board."

    @staticmethod
    def unknown_response() -> str:
        return "Nao entendi bem. Voce quer falar sobre: 1. Status, 2. Criar/Atualizar tarefa, ou 3. Duvida sobre o board?"

    @staticmethod
    def error_response() -> str:
        return "Nao consegui processar sua mensagem agora. Tente novamente em instantes."

    @staticmethod
    def _format_payload_lines(payload: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
        labels = {
            "title": "Titulo",
            "description": "Descricao",
            "assignee": "Responsavel",
            "priority": "Prioridade",
            "due_date": "Prazo",
            "project": "Projeto",
            "status": "Status",
        }
        lines = []
        for key in keys:
            value = payload.get(key)
            if value:
                lines.append(f"- {labels[key]}: {value}")
        return lines

    def _status_board_response(self, board_context: Any) -> str:
        if isinstance(board_context, str):
            return board_context
        if not isinstance(board_context, dict):
            return f"Consultei o status do board: {board_context}"

        keys = {
            "progress": "Andamento",
            "status": "Status",
            "open_tasks": "Tarefas abertas",
            "blockers": "Bloqueios",
            "next_steps": "Proximos passos",
        }
        lines = []
        for key, label in keys.items():
            value = board_context.get(key)
            if value:
                lines.append(f"{label}: {value}")
        if lines:
            return "\n".join(lines)
        return "Consultei o board, mas o MCP nao retornou dados suficientes para montar um resumo objetivo."


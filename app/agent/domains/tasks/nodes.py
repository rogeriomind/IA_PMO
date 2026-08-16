from __future__ import annotations

from typing import Any

from app.agent.context import ToolExecutionContext
from app.agent.intents import INTENT_TO_TOOL
from app.agent.mcp_gateway import MCPGateway
from app.agent.state import AgentState
from app.mcp.board_tools import normalize_priority, normalize_status
from app.storage.repository import PendingActionRepository


class TaskQueryNodes:
    def __init__(self, gateway: MCPGateway):
        self.gateway = gateway

    async def validate_query(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "task.search")
        entities = state.get("entities") or {}
        missing = list(state.get("missing_fields") or [])
        if intent == "task.get" and not (entities.get("task_id") or entities.get("id")):
            missing.append("task")
        return {"missing_fields": sorted(set(missing))}

    async def resolve_parameters(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "task.search")
        entities = state.get("entities") or {}
        metadata = state.get("metadata") or {}
        project_id = entities.get("project_id") or metadata.get("project_id") or metadata.get("projectId")
        if intent == "task.get":
            tool_input = {"id": entities.get("task_id") or entities.get("id")}
        elif intent == "user.my_tasks":
            tool_input = {"user_id": state["user_id"], "project_id": project_id}
        else:
            tool_input = {
                "search": entities.get("search") or entities.get("query") or state.get("normalized_message", ""),
                "project_id": project_id,
            }
        return {"tool_input": {key: value for key, value in tool_input.items() if value is not None}}

    async def select_read_tool(self, state: AgentState) -> AgentState:
        return {"selected_tool": INTENT_TO_TOOL[state.get("intent", "task.search")]}

    async def execute_tool(self, state: AgentState) -> AgentState:
        if state.get("missing_fields"):
            return {}
        result = await self.gateway.execute(
            tool_name=state["selected_tool"],
            arguments=state.get("tool_input") or {},
            context=_context(state, approval_status="not_required"),
        )
        return {"tool_result": result.model_dump(), "data": {"result": result.result}}

    async def normalize_result(self, state: AgentState) -> AgentState:
        return {}

    async def format_domain_result(self, state: AgentState) -> AgentState:
        if state.get("missing_fields"):
            return {"final_answer": "Preciso do ID ou titulo da tarefa para consultar.", "status": "completed"}
        result = (state.get("tool_result") or {}).get("result")
        if state.get("intent") == "user.my_tasks":
            return {"final_answer": _format_list_response(result, "Encontrei suas tarefas:"), "status": "completed"}
        if state.get("intent") == "task.get":
            return {"final_answer": _format_task_response(result), "status": "completed"}
        return {"final_answer": _format_list_response(result, "Consultei o board e encontrei:"), "status": "completed"}


class TaskWriteNodes:
    def __init__(self, gateway: MCPGateway, repository: PendingActionRepository):
        self.gateway = gateway
        self.repository = repository

    async def extract_write_parameters(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "")
        entities = state.get("entities") or {}
        metadata = state.get("metadata") or {}
        project = entities.get("project") or entities.get("project_id") or metadata.get("project_id") or metadata.get("projectId")

        if intent == "task.create":
            tool_input = {
                "title": entities.get("title"),
                "description": entities.get("description") or entities.get("title"),
                "assignee": entities.get("assignee"),
                "priority": normalize_priority(entities.get("priority")) if entities.get("priority") else None,
                "due_date": entities.get("due_date"),
                "project": project,
                "status": normalize_status(entities.get("status")) if entities.get("status") else None,
            }
        elif intent == "task.update":
            fields = dict(entities.get("fields") or {})
            if "priority" in fields:
                fields["priority"] = normalize_priority(fields["priority"])
            if "status" in fields:
                fields["status"] = normalize_status(fields["status"])
            tool_input = {
                "task_id": entities.get("task_id"),
                "task_query": entities.get("task_query"),
                "fields": fields,
            }
        elif intent == "task.move":
            tool_input = {
                "task_id": entities.get("task_id"),
                "task_query": entities.get("task_query"),
                "status": normalize_status(entities.get("status")) if entities.get("status") else None,
            }
        else:
            tool_input = {
                "task_id": entities.get("task_id"),
                "task_query": entities.get("task_query"),
                "comment": entities.get("comment"),
            }

        return {
            "selected_tool": INTENT_TO_TOOL[intent],
            "tool_input": {key: value for key, value in tool_input.items() if value not in (None, {}, [])},
        }

    async def validate_required_fields(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "")
        data = state.get("tool_input") or {}
        missing: list[str] = []
        if intent == "task.create" and not data.get("title"):
            missing.append("title")
        if intent in {"task.update", "task.move", "task.comment"} and not (data.get("task_id") or data.get("task_query")):
            missing.append("task")
        if intent == "task.update" and not data.get("fields"):
            missing.append("fields")
        if intent == "task.move" and not data.get("status"):
            missing.append("status")
        if intent == "task.comment" and not data.get("comment"):
            missing.append("comment")
        return {"missing_fields": missing}

    async def validate_business_rules(self, state: AgentState) -> AgentState:
        return {}

    async def load_current_task(self, state: AgentState) -> AgentState:
        data = state.get("tool_input") or {}
        task_id = data.get("task_id")
        if not task_id or state.get("intent") == "task.create":
            return {}
        try:
            result = await self.gateway.execute(
                tool_name="board_get_task",
                arguments={"id": task_id},
                context=_context(state, intent="task.get", approval_status="not_required"),
            )
            return {"data": {"current_task": result.result}}
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append({"code": "CURRENT_TASK_READ_FAILED", "message": str(exc)})
            return {"errors": errors}

    async def build_action_preview(self, state: AgentState) -> AgentState:
        preview = {
            "tool": state.get("selected_tool"),
            "intent": state.get("intent"),
            "arguments": state.get("tool_input") or {},
        }
        return {
            "action_preview": preview,
            "requires_confirmation": True,
            "approval_status": state.get("approval_status") or "pending",
        }

    async def interrupt_for_confirmation(self, state: AgentState) -> AgentState:
        if state.get("missing_fields"):
            return {
                "status": "completed",
                "final_answer": _missing_fields_message(state.get("missing_fields") or []),
            }
        if state.get("approval_status") == "approved":
            return {}
        preview = state.get("action_preview") or {}
        pending = self.repository.create_pending_action(
            conversation_id=state["thread_id"],
            user_id=state["user_id"],
            action_type=state["selected_tool"],
            action_payload={
                "tool_input": state.get("tool_input") or {},
                "intent": state.get("intent"),
                "tenant_id": state.get("tenant_id"),
                "request_id": state.get("request_id"),
                "correlation_id": state.get("correlation_id"),
                "preview": preview,
            },
        )
        return {
            "confirmation_id": pending["id"],
            "approval_status": "pending",
            "status": "awaiting_confirmation",
            "final_answer": _confirmation_message(state.get("selected_tool", ""), state.get("tool_input") or {}),
        }

    async def execute_write_tool(self, state: AgentState) -> AgentState:
        if state.get("status") == "awaiting_confirmation" or state.get("missing_fields"):
            return {}
        result = await self.gateway.execute(
            tool_name=state["selected_tool"],
            arguments=state.get("tool_input") or {},
            context=_context(
                state,
                approval_status="approved",
                idempotency_key=state.get("idempotency_key"),
            ),
        )
        return {"tool_result": result.model_dump(), "data": {"result": result.result}}

    async def read_after_write(self, state: AgentState) -> AgentState:
        if not state.get("tool_result") or state.get("selected_tool") == "board_create_task":
            return {}
        data = state.get("tool_input") or {}
        task_id = data.get("task_id") or data.get("id")
        result_payload = (state.get("tool_result") or {}).get("result")
        if not task_id and isinstance(result_payload, dict):
            task_id = result_payload.get("id") or result_payload.get("task_id")
        if not task_id:
            return {}
        try:
            read_result = await self.gateway.execute(
                tool_name="board_get_task",
                arguments={"id": task_id},
                context=_context(state, intent="task.get", approval_status="not_required"),
            )
            return {"read_after_write_result": read_result.result}
        except Exception as exc:
            errors = list(state.get("errors") or [])
            errors.append({"code": "READ_AFTER_WRITE_FAILED", "message": str(exc)})
            return {"errors": errors}

    async def validate_final_state(self, state: AgentState) -> AgentState:
        return {}

    async def format_domain_result(self, state: AgentState) -> AgentState:
        if state.get("final_answer"):
            return {}
        selected = state.get("selected_tool", "")
        message = {
            "board_create_task": "Tarefa criada com sucesso no board.",
            "board_update_task": "Tarefa atualizada com sucesso no board.",
            "board_move_task": "Tarefa movida com sucesso no board.",
            "board_add_comment": "Comentario adicionado com sucesso no board.",
        }.get(selected, "Acao executada com sucesso no board.")
        if state.get("errors"):
            message += " A leitura de verificacao nao confirmou o estado final automaticamente."
        return {"final_answer": message, "status": "completed"}


def _context(
    state: AgentState,
    *,
    intent: str | None = None,
    approval_status: str = "not_required",
    idempotency_key: str | None = None,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        request_id=state["request_id"],
        correlation_id=state["correlation_id"],
        thread_id=state["thread_id"],
        tenant_id=state["tenant_id"],
        user_id=state["user_id"],
        api_version=state.get("api_version", "v1"),
        user_roles=state.get("user_roles") or [],
        intent=intent or state.get("intent", "unknown"),
        approval_status=approval_status,
        idempotency_key=idempotency_key,
    )


def _format_task_response(result: Any) -> str:
    if isinstance(result, dict):
        title = result.get("title") or result.get("name") or result.get("id") or "tarefa"
        status = result.get("status")
        if status:
            return f"A tarefa {title} esta em {status}."
        return f"Encontrei a tarefa {title}."
    return f"Consultei a tarefa: {result}"


def _format_list_response(result: Any, prefix: str) -> str:
    if isinstance(result, list):
        if not result:
            return "Nao encontrei tarefas para essa consulta."
        lines = [prefix]
        for item in result[:5]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('id', '')} {item.get('title') or item.get('name') or item}")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines)
    if isinstance(result, dict):
        tasks = result.get("tasks") or result.get("items") or result.get("data")
        if isinstance(tasks, list):
            return _format_list_response(tasks, prefix)
    return f"{prefix} {result}"


def _missing_fields_message(missing: list[str]) -> str:
    if "title" in missing:
        return "Qual e o titulo da tarefa?"
    if "task" in missing:
        return "Qual tarefa voce quer alterar? Envie o ID ou o titulo."
    if "status" in missing:
        return "Para qual status voce quer mover essa tarefa?"
    if "comment" in missing:
        return "Qual comentario voce quer adicionar?"
    if "fields" in missing:
        return "O que voce quer atualizar nessa tarefa?"
    return "Preciso de mais detalhes para continuar."


def _confirmation_message(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == "board_create_task":
        return f"Vou criar a tarefa '{arguments.get('title')}'. Confirma?"
    if tool_name == "board_move_task":
        target = arguments.get("task_id") or arguments.get("task_query")
        return f"Vou mover a tarefa {target} para {arguments.get('status')}. Confirma?"
    if tool_name == "board_update_task":
        target = arguments.get("task_id") or arguments.get("task_query")
        return f"Vou atualizar a tarefa {target} com {arguments.get('fields')}. Confirma?"
    if tool_name == "board_add_comment":
        target = arguments.get("task_id") or arguments.get("task_query")
        return f"Vou adicionar um comentario na tarefa {target}. Confirma?"
    return "Vou executar esta alteracao no board. Confirma?"

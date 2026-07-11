from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.errors import AgentError
from app.agent.intents import READ_INTENTS, WRITE_INTENTS
from app.agent.routing import DeterministicRouter, HybridIntentRouter
from app.agent.state import AgentState
from app.config import Settings
from app.storage.repository import PendingActionRepository

logger = logging.getLogger(__name__)


class MainGraphNodes:
    def __init__(
        self,
        *,
        settings: Settings,
        router: HybridIntentRouter,
        repository: PendingActionRepository,
    ) -> None:
        self.settings = settings
        self.router = router
        self.deterministic = DeterministicRouter()
        self.repository = repository

    async def load_context(self, state: AgentState) -> AgentState:
        return {
            "metadata": state.get("metadata") or {},
            "user_roles": state.get("user_roles") or [],
            "errors": state.get("errors") or [],
            "retry_count": state.get("retry_count") or 0,
            "approval_status": state.get("approval_status") or "not_required",
            "status": state.get("status") or "completed",
        }

    async def authenticate_and_authorize(self, state: AgentState) -> AgentState:
        if not state.get("tenant_id") or not state.get("user_id"):
            errors = list(state.get("errors") or [])
            errors.append({"code": "AUTH_CONTEXT_MISSING", "message": "Contexto autenticado ausente."})
            return {"errors": errors, "status": "error"}
        return {}

    async def normalize_message(self, state: AgentState) -> AgentState:
        original = state.get("original_message", "")
        normalized = re.sub(r"\s+", " ", original).strip()
        if len(normalized) > self.settings.agent_max_message_chars:
            normalized = normalized[: self.settings.agent_max_message_chars]
        return {"normalized_message": normalized}

    async def deterministic_router(self, state: AgentState) -> AgentState:
        classification = self.deterministic.route(state.get("normalized_message", ""))
        if classification and classification.confidence >= self.settings.agent_intent_confidence_threshold:
            return {
                "intent": classification.intent,
                "confidence": classification.confidence,
                "entities": classification.entities,
                "missing_fields": classification.missing_fields,
                "requires_confirmation": classification.requires_confirmation,
                "reasoning_summary": classification.reasoning_summary,
                "route": "classified",
            }
        return {"route": "needs_llm"}

    async def classify_and_extract(self, state: AgentState) -> AgentState:
        if state.get("route") == "classified":
            return {}
        classification = await self.router.classify(state.get("normalized_message", ""))
        return {
            "intent": classification.intent,
            "confidence": classification.confidence,
            "entities": classification.entities,
            "missing_fields": classification.missing_fields,
            "requires_confirmation": classification.requires_confirmation,
            "reasoning_summary": classification.reasoning_summary,
        }

    async def validate_classification(self, state: AgentState) -> AgentState:
        intent = state.get("intent") or "unknown"
        confidence = float(state.get("confidence") or 0)
        if confidence < self.settings.agent_intent_confidence_threshold and intent != "help":
            return {
                "intent": "unknown",
                "requires_confirmation": False,
                "missing_fields": [],
            }
        if intent in WRITE_INTENTS:
            return {"requires_confirmation": True}
        return {"requires_confirmation": False}

    async def route_intent(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "unknown")
        if intent in {"task.search", "task.get", "user.my_tasks"}:
            return {"route": "task_query"}
        if intent in WRITE_INTENTS:
            return {"route": "task_write"}
        if intent in {"project.status", "project.blockers"}:
            return {"route": "project"}
        return {"route": "respond"}

    async def help_or_unknown(self, state: AgentState) -> AgentState:
        if state.get("intent") == "help":
            return {
                "status": "completed",
                "final_answer": (
                    "Posso consultar tarefas, status e bloqueios do projeto, alem de preparar criacao, "
                    "atualizacao, movimentacao e comentarios em tarefas mediante confirmacao."
                ),
            }
        return {
            "status": "completed",
            "final_answer": "Nao entendi com seguranca. Voce quer consultar tarefas, status do projeto ou alterar uma tarefa?",
        }

    async def validate_tool_result(self, state: AgentState) -> AgentState:
        return {}

    async def format_response(self, state: AgentState) -> AgentState:
        if state.get("final_answer"):
            return {}
        if state.get("errors"):
            return {
                "status": "error",
                "final_answer": "Nao consegui processar sua mensagem agora.",
            }
        return {
            "status": state.get("status") or "completed",
            "final_answer": "Solicitacao processada.",
        }

    async def persist_execution_metadata(self, state: AgentState) -> AgentState:
        try:
            self.repository.append_tool_execution_audit(
                request_id=state["request_id"],
                correlation_id=state["correlation_id"],
                thread_id=state["thread_id"],
                tenant_id=state["tenant_id"],
                user_id=state["user_id"],
                intent=state.get("intent", "unknown"),
                tool_name=state.get("selected_tool") or "none",
                tool_type="workflow",
                status=state.get("status") or "completed",
                latency_ms=0,
                arguments={"route": state.get("route")},
                result={"confirmation_id": state.get("confirmation_id")},
                error_code=(state.get("errors") or [{}])[0].get("code") if state.get("errors") else None,
            )
        except Exception:
            logger.exception("Failed to persist workflow metadata")
        return {}

    async def handle_error(self, state: AgentState) -> AgentState:
        return {"status": "error", "final_answer": "Nao consegui processar sua mensagem agora."}


def safe_error_state(exc: Exception, state: AgentState) -> AgentState:
    code = getattr(exc, "code", "AGENT_ERROR")
    message = exc.user_message if isinstance(exc, AgentError) else "Nao consegui processar sua mensagem agora."
    errors = list(state.get("errors") or [])
    errors.append({"code": code, "message": str(exc)})
    return {"errors": errors, "status": "error", "final_answer": message}


from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.graph.prompts import CLASSIFIER_SYSTEM_PROMPT, EXTRACTOR_SYSTEM_PROMPT
from app.schemas import Intent, IntentClassification, TaskEntities

logger = logging.getLogger(__name__)


class IntentService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._classifier = None
        self._extractor = None

        if settings.llm_configured:
            try:
                from langchain_openai import ChatOpenAI

                llm = ChatOpenAI(
                    model=settings.llm_model,
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    timeout=30,
                )
                self._classifier = llm.with_structured_output(IntentClassification)
                self._extractor = llm.with_structured_output(TaskEntities)
            except Exception:
                logger.exception("%s/LangChain initialization failed; local fallback will be used", settings.llm_provider)
        else:
            logger.warning("LLM provider, API key or model is not configured; local fallback will be used")

    async def classify(self, message: str) -> IntentClassification:
        if self._classifier:
            try:
                result = await self._classifier.ainvoke(
                    [
                        ("system", CLASSIFIER_SYSTEM_PROMPT),
                        ("human", message),
                    ]
                )
                classification = IntentClassification.model_validate(result)
                local = self._classify_locally(message)
                if classification.intent == Intent.UNKNOWN and local.intent != Intent.UNKNOWN:
                    return local
                return classification
            except Exception:
                logger.exception("Intent classification via %s failed; using local fallback", self.settings.llm_provider)
        return self._classify_locally(message)

    async def extract_entities(self, message: str, intent: Intent) -> TaskEntities:
        if self._extractor:
            try:
                result = await self._extractor.ainvoke(
                    [
                        ("system", EXTRACTOR_SYSTEM_PROMPT),
                        ("human", f"Intent: {intent.value}\nMensagem: {message}"),
                    ]
                )
                entities = TaskEntities.model_validate(result)
                local_entities = self._extract_locally(message, intent)
                return self._merge_entities(entities, local_entities)
            except Exception:
                logger.exception("Entity extraction via %s failed; using local fallback", self.settings.llm_provider)
        return self._extract_locally(message, intent)

    async def check_llm_model(self) -> dict[str, Any]:
        if not self.settings.llm_configured:
            return {
                "provider": self.settings.llm_provider,
                "configured": False,
                "available": False,
                "error": "LLM API key or model not configured",
            }
        try:
            from openai import AsyncOpenAI

            client_kwargs = {"api_key": self.settings.llm_api_key.get_secret_value()}
            if self.settings.llm_base_url:
                client_kwargs["base_url"] = self.settings.llm_base_url
            client = AsyncOpenAI(**client_kwargs)
            if self.settings.llm_provider == "openai":
                await client.models.retrieve(self.settings.llm_model)
            else:
                await client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=[{"role": "user", "content": "health"}],
                    max_tokens=1,
                )
            return {
                "provider": self.settings.llm_provider,
                "configured": True,
                "available": True,
                "error": None,
            }
        except Exception as exc:
            logger.exception("%s model availability check failed", self.settings.llm_provider)
            return {
                "provider": self.settings.llm_provider,
                "configured": True,
                "available": False,
                "error": str(exc),
            }

    def _classify_locally(self, message: str) -> IntentClassification:
        text = message.casefold().strip()

        if re.search(r"\b(cria|criar|nova tarefa|novo card|adiciona|abrir tarefa|abre uma tarefa)\b", text):
            return IntentClassification(intent=Intent.TASK_CREATE, confidence=0.9, reason="Pedido de criacao de tarefa")

        if re.search(r"\b(move|mover|muda|alterar status|troca.*status|coloca)\b", text) and re.search(
            r"\b(tarefa|task|card|para)\b", text
        ):
            return IntentClassification(intent=Intent.TASK_MOVE, confidence=0.86, reason="Pedido de movimentacao de tarefa")

        if re.search(r"\b(comenta|coment[aá]rio|adiciona coment[aá]rio)\b", text):
            return IntentClassification(intent=Intent.TASK_COMMENT, confidence=0.84, reason="Pedido de comentario em tarefa")

        if re.search(
            r"\b(atualiza|atualizar|altera|alterar|altere|edita|muda prioridade|muda data|troca respons|troca data)\b",
            text,
        ):
            return IntentClassification(intent=Intent.TASK_UPDATE, confidence=0.82, reason="Pedido de atualizacao de tarefa")

        if re.search(r"\b(status|andamento|resumo|bloqueios?|proximos passos|pr[oó]ximos passos)\b", text):
            return IntentClassification(intent=Intent.STATUS_BOARD, confidence=0.86, reason="Pedido de status do board")

        if re.search(r"\b(qual|quais|quem|quantas|quantos|listar|lista|mostra|me mostra|tem tarefa)\b", text):
            return IntentClassification(intent=Intent.BOARD_QUESTION, confidence=0.74, reason="Pergunta sobre dados do board")

        if re.search(r"\b(oi|ola|olá|bom dia|boa tarde|boa noite|obrigad[oa]|valeu)\b", text):
            return IntentClassification(intent=Intent.SMALLTALK, confidence=0.78, reason="Saudacao ou conversa curta")

        return IntentClassification(intent=Intent.UNKNOWN, confidence=0.4, reason="Mensagem ambigua")

    def _extract_locally(self, message: str, intent: Intent) -> TaskEntities:
        entities = TaskEntities()
        original = message.strip()
        text = original.casefold()

        entities.priority = self._extract_priority(text)
        entities.status = self._extract_status(original)
        entities.due_date = self._extract_due_date(original)
        entities.assignee = self._extract_assignee(original)
        entities.project = self._extract_project(original)

        if intent == Intent.TASK_CREATE:
            entities.title = self._extract_create_title(original)
            entities.description = entities.title
        elif intent in {Intent.TASK_UPDATE, Intent.TASK_MOVE, Intent.TASK_COMMENT}:
            task_ref = self._extract_task_reference(original)
            if task_ref:
                if self._looks_like_id(task_ref):
                    entities.task_id = task_ref
                else:
                    entities.task_query = task_ref
            if intent == Intent.TASK_COMMENT:
                entities.comment = self._extract_comment(original)
            if intent == Intent.TASK_UPDATE:
                fields = {}
                for key in ("priority", "status", "due_date", "assignee"):
                    value = getattr(entities, key)
                    if value:
                        fields[key] = value
                entities.fields = fields

        return entities

    @staticmethod
    def _extract_priority(text: str) -> str | None:
        if "urgente" in text:
            return "urgente"
        for priority in ("alta", "media", "média", "baixa"):
            if re.search(rf"\bprioridade\s+{priority}\b|\b{priority}\s+prioridade\b", text):
                return "media" if priority == "média" else priority
        return None

    @staticmethod
    def _extract_status(message: str) -> str | None:
        match = re.search(
            r"\bpara\s+(em andamento|conclu[ií]d[ao]|feito|done|a fazer|todo|bloquead[ao]|revis[aã]o|review)\b",
            message,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_due_date(message: str) -> str | None:
        relative = re.search(r"\bpara\s+(hoje|amanh.)\b", message, flags=re.IGNORECASE)
        if relative:
            base = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
            if relative.group(1).casefold().startswith("amanh"):
                base = base + timedelta(days=1)
            return base.isoformat()

        date_match = re.search(r"\bpara\s+(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b", message)
        if date_match:
            return IntentService._normalize_date(date_match.group(1))

        match = re.search(r"\bprazo\s+(?:para\s+)?([^,.;]+)", message, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_assignee(message: str) -> str | None:
        match = re.search(r"\brespons[aá]vel\s+([^,.;]+)", message, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_project(message: str) -> str | None:
        match = re.search(r"\bprojeto\s+([^,.;]+)", message, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    @classmethod
    def _extract_create_title(cls, message: str) -> str | None:
        match = re.search(
            r"\b(?:cria|criar|adicione|adiciona|abrir|abre)\s+(?:uma\s+)?(?:nova\s+)?tarefa(?:\s+para|:)?\s*(.+)?$",
            message,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        title = (match.group(1) or "").strip(" .")
        title = cls._strip_title_qualifiers(title)
        if not title or title.casefold() in {"uma tarefa", "tarefa", "nova tarefa"}:
            return None
        return title

    @staticmethod
    def _strip_title_qualifiers(title: str) -> str:
        patterns = [
            r"\s+com\s+prioridade\s+(?:alta|m[eé]dia|baixa|urgente)\b.*$",
            r"\s+prioridade\s+(?:alta|m[eé]dia|baixa|urgente)\b.*$",
            r"\s+prazo\s+(?:para\s+)?[^,.;]+$",
            r"\s+respons[aá]vel\s+[^,.;]+$",
        ]
        cleaned = title.strip()
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned or title.strip()

    @staticmethod
    def _extract_task_reference(message: str) -> str | None:
        patterns = [
            r"\b(?:data|prazo|vencimento)\s+d[ao]\s+(.+?)\s+para\s+",
            r"\b(?:tarefa|task|card)\s+(.+?)\s+para\s+",
            r"\b(?:tarefa|task|card)\s+(.+?)(?:\s+com|\s*:|$)",
            r"\b#([A-Za-z0-9_-]+)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip(" .:")
        return None

    @staticmethod
    def _extract_comment(message: str) -> str | None:
        match = re.search(r"(?:coment[aá]rio|comenta(?:r)?)(?:\s+na\s+tarefa\s+.+?)?\s*[:\-]\s*(.+)$", message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r"\bcom\s+coment[aá]rio\s+(.+)$", message, re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _looks_like_id(value: str) -> bool:
        return bool(re.fullmatch(r"#?[A-Z]{1,10}-?\d{1,10}|[0-9a-fA-F-]{24,36}", value.strip()))

    @staticmethod
    def _normalize_date(value: str) -> str:
        clean = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", clean):
            return clean
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", clean)
        if not match:
            return clean
        day, month, year = match.groups()
        if len(year) == 2:
            year = "20" + year
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    @staticmethod
    def _merge_entities(primary: TaskEntities, fallback: TaskEntities) -> TaskEntities:
        merged = primary.model_copy(deep=True)
        for field_name in TaskEntities.model_fields:
            primary_value = getattr(merged, field_name)
            fallback_value = getattr(fallback, field_name)
            if primary_value in (None, {}, []) and fallback_value not in (None, {}, []):
                setattr(merged, field_name, fallback_value)
        if not merged.fields and fallback.fields:
            merged.fields = fallback.fields
        return merged

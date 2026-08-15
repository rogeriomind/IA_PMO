from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.agent.extraction.schemas import CreateTaskExtraction, DateExtraction, UpdateTaskExtraction
from app.agent.latency import record_llm_call
from app.config import Settings
from app.mcp.board_tools import normalize_priority
from app.observability.llm_usage import (
    chat_model_kwargs,
    estimate_cost_details,
    extract_usage_details,
    structured_output_kwargs,
    unwrap_structured_output,
)
from app.observability.langfuse import LangfuseTracer, TraceContext

logger = logging.getLogger(__name__)


CREATE_SYSTEM_PROMPT = """
Extraia campos para criar uma atividade PMO.
Regras: extraia somente informacoes presentes; nao invente tarefa, pessoa, data ou ID;
nao escolha ferramenta; nao execute acoes; retorne null para informacao ausente;
resolva datas relativas usando a data atual informada; considere America/Sao_Paulo.
"""

UPDATE_SYSTEM_PROMPT = """
Extraia campos para atualizar uma atividade PMO.
Campos liberados agora: due_date, assignee e comment. Nao libere outros campos.
Nao invente tarefa, pessoa, data ou ID; nao escolha ferramenta; nao execute acoes;
retorne null para informacao ausente; callbacks de botao nao devem ser interpretados.
"""


class TaskExtractionService:
    def __init__(self, settings: Settings, tracer: LangfuseTracer | None = None):
        self.settings = settings
        self.tracer = tracer
        self._create_llm = None
        self._update_llm = None
        if settings.llm_configured:
            try:
                from langchain_openai import ChatOpenAI

                llm = ChatOpenAI(
                    model=settings.llm_model,
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    timeout=30,
                    **chat_model_kwargs(settings.llm_provider),
                )
                kwargs = structured_output_kwargs(settings.llm_provider)
                self._create_llm = llm.with_structured_output(CreateTaskExtraction, **kwargs)
                self._update_llm = llm.with_structured_output(UpdateTaskExtraction, **kwargs)
            except Exception:
                logger.exception("Task extraction LLM initialization failed; local extraction enabled")

    async def extract_create(
        self,
        text: str,
        *,
        today: date | None = None,
        timezone: str = "America/Sao_Paulo",
        trace: TraceContext | None = None,
    ) -> CreateTaskExtraction:
        base_date = today or _today(timezone)
        if self._create_llm:
            try:
                messages = [
                    ("system", CREATE_SYSTEM_PROMPT),
                    (
                        "human",
                        f"Data atual: {base_date.isoformat()}\nTimezone: {timezone}\nMensagem: {text}",
                    ),
                ]
                generation = self._generation(
                    trace,
                    "task_create.extract",
                    input_payload=messages,
                    metadata={
                        "provider": self.settings.llm_provider,
                        "schema": "CreateTaskExtraction",
                        "timezone": timezone,
                    },
                )
                with generation as observation:
                    llm_started = time.perf_counter()
                    llm_success = False
                    try:
                        result = await self._create_llm.ainvoke(messages)
                        llm_success = True
                    finally:
                        record_llm_call(
                            name="task_create.extract",
                            duration_ms=int((time.perf_counter() - llm_started) * 1000),
                            success=llm_success,
                        )
                    llm = CreateTaskExtraction.model_validate(unwrap_structured_output(result))
                    self._update_observation(
                        observation,
                        output=llm.model_dump(mode="json"),
                        usage_details=extract_usage_details(result),
                    )
                local = _extract_create_locally(text, base_date)
                return _merge_create(llm, local)
            except Exception:
                logger.exception("Create extraction via LLM failed; using local fallback")
        return _extract_create_locally(text, base_date)

    async def extract_update(
        self,
        text: str,
        *,
        today: date | None = None,
        timezone: str = "America/Sao_Paulo",
        trace: TraceContext | None = None,
    ) -> UpdateTaskExtraction:
        base_date = today or _today(timezone)
        if self._update_llm:
            try:
                messages = [
                    ("system", UPDATE_SYSTEM_PROMPT),
                    (
                        "human",
                        f"Data atual: {base_date.isoformat()}\nTimezone: {timezone}\nMensagem: {text}",
                    ),
                ]
                generation = self._generation(
                    trace,
                    "task_update.extract",
                    input_payload=messages,
                    metadata={
                        "provider": self.settings.llm_provider,
                        "schema": "UpdateTaskExtraction",
                        "timezone": timezone,
                    },
                )
                with generation as observation:
                    llm_started = time.perf_counter()
                    llm_success = False
                    try:
                        result = await self._update_llm.ainvoke(messages)
                        llm_success = True
                    finally:
                        record_llm_call(
                            name="task_update.extract",
                            duration_ms=int((time.perf_counter() - llm_started) * 1000),
                            success=llm_success,
                        )
                    llm = UpdateTaskExtraction.model_validate(unwrap_structured_output(result))
                    self._update_observation(
                        observation,
                        output=llm.model_dump(mode="json"),
                        usage_details=extract_usage_details(result),
                    )
                local = _extract_update_locally(text, base_date)
                return _merge_update(llm, local)
            except Exception:
                logger.exception("Update extraction via LLM failed; using local fallback")
        return _extract_update_locally(text, base_date)

    async def extract_date(
        self,
        text: str,
        *,
        today: date | None = None,
        timezone: str = "America/Sao_Paulo",
    ) -> DateExtraction:
        base_date = today or _today(timezone)
        return DateExtraction(due_date=_extract_due_date(text, base_date))

    def _generation(
        self,
        trace: TraceContext | None,
        name: str,
        *,
        input_payload: Any,
        metadata: dict[str, Any],
    ):
        if self.tracer:
            return self.tracer.generation(
                trace,
                name,
                input_payload=input_payload,
                metadata=metadata,
                model=self.settings.llm_model,
                model_parameters={"timeout": 30},
            )
        from contextlib import nullcontext

        return nullcontext(None)

    def _update_observation(
        self,
        observation: Any | None,
        *,
        output: Any,
        usage_details: dict[str, int] | None = None,
    ) -> None:
        if self.tracer and observation:
            cost_details = estimate_cost_details(
                usage_details or {},
                provider=self.settings.llm_provider,
                model=self.settings.llm_model,
            )
            self.tracer.update_observation(
                observation,
                output=output,
                usage_details=usage_details or None,
                cost_details=cost_details or None,
            )


def _today(timezone: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except Exception:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _plain(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def _extract_create_locally(text: str, today: date) -> CreateTaskExtraction:
    title = _extract_create_title(text)
    due_date = _extract_due_date(text, today)
    assignee = _extract_assignee(text)
    priority = _extract_priority(text)
    description = _extract_description(text)
    return CreateTaskExtraction(
        title=title,
        due_date=due_date,
        assignee_name=assignee,
        priority=priority,
        description=description,
    )


def _extract_update_locally(text: str, today: date) -> UpdateTaskExtraction:
    fields: dict[str, str | None] = {}
    due_date = _extract_due_date(text, today)
    if due_date:
        fields["due_date"] = due_date
    assignee = _extract_assignee(text)
    if assignee:
        fields["assignee"] = assignee
    task_id = _extract_task_id(text)
    task_number = _extract_leading_number(text)
    comment = _extract_comment(text)
    return UpdateTaskExtraction(
        task_id=task_id,
        task_number=task_number,
        fields=fields,
        assignee_name=assignee,
        comment=comment,
    )


def _extract_create_title(text: str) -> str | None:
    cleaned = re.sub(
        r"^\s*(criar|cria|adicione|adiciona|abrir|abre)\s+(uma\s+)?(nova\s+)?(atividade|tarefa|card)?\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    ).strip(" :.-")
    if not cleaned or _plain(cleaned) in {"atividade", "tarefa", "card"}:
        return None
    stop_patterns = [
        r"\s+para\s+(hoje|amanh[aã]|segunda(?:-feira)?|ter[cç]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|sabado|s[aá]bado|domingo)\b.*$",
        r"\s+com\s+data\s+[^,.;]+.*$",
        r"\s+data\s+[^,.;]+.*$",
        r"\s+vencimento\s+[^,.;]+.*$",
        r"\s+respons[aá]vel\s+[^,.;]+.*$",
        r"\s+prioridade\s+[^,.;]+.*$",
        r"\s*,\s*respons[aá]vel\s+.*$",
        r"\s*,\s*prioridade\s+.*$",
    ]
    for pattern in stop_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip(" ,.;")
    return cleaned or None


def _extract_due_date(text: str, today: date) -> str | None:
    normalized = _plain(text)
    if re.search(r"\bhoje\b", normalized):
        return today.isoformat()
    if re.search(r"\bamanha\b", normalized):
        return (today + timedelta(days=1)).isoformat()

    weekdays = {
        "segunda": 0,
        "segunda feira": 0,
        "terca": 1,
        "terca feira": 1,
        "quarta": 2,
        "quarta feira": 2,
        "quinta": 3,
        "quinta feira": 3,
        "sexta": 4,
        "sexta feira": 4,
        "sabado": 5,
        "domingo": 6,
    }
    for name, weekday in weekdays.items():
        if re.search(rf"\b{name}\b", normalized):
            days = (weekday - today.weekday()) % 7
            if days == 0:
                days = 7
            return (today + timedelta(days=days)).isoformat()

    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if match:
        return match.group(1)

    match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if match:
        day, month, year = match.groups()
        year = year or str(today.year)
        if len(year) == 2:
            year = "20" + year
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def _extract_assignee(text: str) -> str | None:
    match = re.search(
        r"\brespons[aá]vel\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][^,.;]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).strip()
    value = re.sub(r"\s+prioridade\s+.*$", "", value, flags=re.IGNORECASE).strip()
    if _plain(value) in {"hoje", "amanha"}:
        return None
    return value or None


def _extract_priority(text: str) -> str | None:
    normalized = _plain(text)
    for raw, normalized_priority in {
        "urgente": "CRITICAL",
        "critica": "CRITICAL",
        "alta": "HIGH",
        "media": "MEDIUM",
        "baixa": "LOW",
    }.items():
        if re.search(rf"\b(prioridade\s+)?{raw}\b", normalized):
            return normalize_priority(normalized_priority)
    return None


def _extract_description(text: str) -> str | None:
    patterns = [
        r"\bobserva[cç][aã]o\s*[:\-]\s*(.+)$",
        r"\bdescri[cç][aã]o\s*[:\-]\s*(.+)$",
        r"\bprecisamos\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .")
            if pattern.startswith(r"\bprecisamos"):
                value = "Precisamos " + value
            return value or None
    return None


def _extract_task_id(text: str) -> str | None:
    match = re.search(r"\b([A-Z]{1,12}-\d{1,12}|TASK-\d+|\d{3,})\b", text)
    if not match:
        return None
    return match.group(1)


def _extract_leading_number(text: str) -> int | None:
    match = re.fullmatch(r"\s*(\d{1,3})\s*", text)
    return int(match.group(1)) if match else None


def _extract_comment(text: str) -> str | None:
    patterns = [
        r"\bcoment[aá]rio\s*[\"':-]?\s*[\"“”]?(.+?)[\"“”]?$",
        r"\badicione\s+o\s+coment[aá]rio\s+[\"“”](.+?)[\"“”]",
        r"\bcomente\s+[\"“”](.+?)[\"“”]",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .\"'“”")
            return value[0].upper() + value[1:] if value else None
    return None


def _merge_create(primary: CreateTaskExtraction, fallback: CreateTaskExtraction) -> CreateTaskExtraction:
    data = primary.model_dump()
    for key, value in fallback.model_dump().items():
        if data.get(key) in (None, "", {}, []) and value not in (None, "", {}, []):
            data[key] = value
    return CreateTaskExtraction.model_validate(data)


def _merge_update(primary: UpdateTaskExtraction, fallback: UpdateTaskExtraction) -> UpdateTaskExtraction:
    data: dict[str, Any] = primary.model_dump()
    fallback_data = fallback.model_dump()
    for key, value in fallback_data.items():
        if key == "fields":
            merged_fields = dict(value or {})
            merged_fields.update(data.get("fields") or {})
            data["fields"] = {k: v for k, v in merged_fields.items() if v is not None}
        elif data.get(key) in (None, "", {}, []) and value not in (None, "", {}, []):
            data[key] = value
    return UpdateTaskExtraction.model_validate(data)

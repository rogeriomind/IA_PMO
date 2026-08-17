from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProjectResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    NOT_REQUIRED = "NOT_REQUIRED"


@dataclass(frozen=True)
class ProjectCandidate:
    project_id: str
    name: str | None = None
    portfolio_id: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class ProjectContextResolution:
    status: ProjectResolutionStatus
    project_id: str | None = None
    project_name: str | None = None
    portfolio_id: str | None = None
    candidates: list[ProjectCandidate] = field(default_factory=list)
    reference: str | None = None


class ProjectContextResolver:
    def __init__(self, *, board_tools: Any | None = None):
        self.board_tools = board_tools

    async def resolve(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session: dict[str, Any],
        entities: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        message_text: str | None = None,
        require_project: bool,
    ) -> ProjectContextResolution:
        del user_id
        entities = entities or {}
        metadata = metadata or {}

        explicit_project_id = _first_string(
            metadata.get("project_id"),
            metadata.get("projectId"),
            entities.get("project_id"),
            entities.get("projectId"),
        )
        if explicit_project_id:
            return ProjectContextResolution(
                status=ProjectResolutionStatus.RESOLVED,
                project_id=explicit_project_id,
            )

        reference = _first_string(
            entities.get("project_reference"),
            entities.get("project"),
            _extract_project_reference(message_text),
        )
        if reference:
            if _looks_like_project_id(reference):
                return ProjectContextResolution(
                    status=ProjectResolutionStatus.RESOLVED,
                    project_id=reference,
                    reference=reference,
                )
            candidates = await self._search_projects(tenant_id=tenant_id, reference=reference)
            if len(candidates) == 1:
                candidate = candidates[0]
                return ProjectContextResolution(
                    status=ProjectResolutionStatus.RESOLVED,
                    project_id=candidate.project_id,
                    project_name=candidate.name,
                    portfolio_id=candidate.portfolio_id,
                    candidates=candidates,
                    reference=reference,
                )
            if len(candidates) > 1:
                return ProjectContextResolution(
                    status=ProjectResolutionStatus.AMBIGUOUS,
                    candidates=candidates,
                    reference=reference,
                )
            return ProjectContextResolution(
                status=ProjectResolutionStatus.NOT_FOUND,
                reference=reference,
            )

        active_project_id = _first_string(session.get("active_project_id"))
        if active_project_id:
            return ProjectContextResolution(
                status=ProjectResolutionStatus.RESOLVED,
                project_id=active_project_id,
                project_name=_first_string(session.get("active_project_name")),
                portfolio_id=_first_string(session.get("active_portfolio_id")),
            )

        return ProjectContextResolution(
            status=ProjectResolutionStatus.NOT_FOUND if require_project else ProjectResolutionStatus.NOT_REQUIRED
        )

    async def _search_projects(self, *, tenant_id: str, reference: str) -> list[ProjectCandidate]:
        if not self.board_tools or not hasattr(self.board_tools, "search_projects"):
            return []
        method = getattr(self.board_tools, "search_projects")
        kwargs = {"tenant_id": tenant_id, "query": reference, "search": reference, "limit": 10}
        try:
            parameters = inspect.signature(method).parameters
            accepted = kwargs
            if not any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
                accepted = {key: value for key, value in kwargs.items() if key in parameters}
            result = await method(**accepted)
        except Exception:
            return []
        return _extract_project_candidates(result)


def _extract_project_reference(text: str | None) -> str | None:
    if not text:
        return None
    patterns = [
        r"\b(?:projeto|project)\s+(?P<ref>[\wÀ-ÿ][\wÀ-ÿ_. -]{1,80})",
        r"\b(?:bloqueios?|status|tarefas|trabalho)\s+(?:do|da|de|no|na)\s+(?P<ref>[\wÀ-ÿ][\wÀ-ÿ_. -]{1,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        reference = match.group("ref").strip(" .,:;!?")
        reference = re.sub(r"^(?:projeto|project)\s+", "", reference, flags=re.IGNORECASE).strip()
        if reference:
            return reference
    return None


def _extract_project_candidates(result: Any) -> list[ProjectCandidate]:
    items: Any = result
    if isinstance(result, dict):
        items = result.get("projects") or result.get("items") or result.get("data") or []
    if not isinstance(items, list):
        return []

    candidates: list[ProjectCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        project_id = _first_string(item.get("projectId"), item.get("project_id"), item.get("id"))
        if not project_id:
            continue
        portfolio = item.get("portfolio")
        candidates.append(
            ProjectCandidate(
                project_id=project_id,
                name=_first_string(item.get("name"), item.get("title")),
                portfolio_id=_first_string(
                    item.get("portfolioId"),
                    item.get("portfolio_id"),
                    portfolio.get("id") if isinstance(portfolio, dict) else None,
                ),
                status=_first_string(item.get("status")),
            )
        )
    return candidates


def _looks_like_project_id(value: str) -> bool:
    text = value.strip()
    return bool(
        re.fullmatch(r"[A-Za-z0-9_.:-]{2,80}", text)
        and (
            re.search(r"\d", text)
            or "-" in text
            or "_" in text
            or re.fullmatch(r"[0-9a-fA-F]{24,36}", text)
        )
    )


def _first_string(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


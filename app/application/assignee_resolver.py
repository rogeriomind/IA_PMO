from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssigneeResolution:
    status: str
    assignee_id: str | None = None
    display_name: str | None = None
    options: list[dict[str, str]] | None = None
    message: str | None = None


class AssigneeResolver:
    """Prepared extension point for a future safe MCP/user-directory lookup.

    The board MCP contract currently exposes no user search tool. This resolver
    only resolves the current user when the name matches safely; it never invents IDs.
    """

    async def resolve(
        self,
        *,
        assignee_name: str | None,
        current_user_id: str,
        current_user_name: str | None,
    ) -> AssigneeResolution:
        if not assignee_name:
            return AssigneeResolution(status="missing")
        if current_user_name and _plain(assignee_name) == _plain(current_user_name):
            return AssigneeResolution(
                status="resolved",
                assignee_id=current_user_id,
                display_name=current_user_name,
            )
        return AssigneeResolution(
            status="unavailable",
            display_name=assignee_name,
            message="Nao ha uma ferramenta MCP segura para resolver usuarios por nome neste ambiente.",
        )


def _plain(value: str) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()

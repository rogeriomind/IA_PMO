from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssigneeResolution:
    status: str
    assignee_id: str | None = None
    display_name: str | None = None
    email: str | None = None
    options: list[dict[str, str | None]] | None = None
    message: str | None = None


class AssigneeResolver:
    def __init__(self, *, board_tools: Any | None = None, repository: Any | None = None):
        self.board_tools = board_tools
        self.repository = repository

    async def resolve(
        self,
        *,
        assignee_name: str | None,
        tenant_id: str | None = None,
        channel: str | None = None,
        provider_user_id: str | None = None,
        current_user_id: str | None = None,
        current_user_name: str | None = None,
        current_username: str | None = None,
    ) -> AssigneeResolution:
        if not assignee_name:
            return AssigneeResolution(status="missing")

        link = self._get_link(tenant_id=tenant_id, channel=channel, provider_user_id=provider_user_id or current_user_id)
        if link and _name_represents_user(
            assignee_name,
            name=link.get("board_user_name"),
            email=link.get("board_user_email"),
            username=current_username,
            current_user_name=current_user_name,
        ):
            return AssigneeResolution(
                status="resolved",
                assignee_id=link["board_user_id"],
                display_name=link.get("board_user_name"),
                email=link.get("board_user_email"),
            )

        users = await self._search_users(assignee_name, tenant_id=tenant_id)
        if not users:
            return AssigneeResolution(
                status="unavailable",
                display_name=assignee_name,
                message="Nao encontrei esse responsavel no Board. Envie nome ou e-mail de um usuario cadastrado.",
            )

        exact_matches = [user for user in users if _matches_exact_user(assignee_name, user)]
        if len(exact_matches) == 1:
            user = exact_matches[0]
            if _is_current_user_candidate(user, current_user_name=current_user_name, current_username=current_username):
                self.link_user(
                    tenant_id=tenant_id,
                    channel=channel,
                    provider_user_id=provider_user_id or current_user_id,
                    user=user,
                    source="auto_exact_current_user",
                )
            return _resolved(user)

        return AssigneeResolution(
            status="needs_selection",
            display_name=assignee_name,
            options=users[:5],
            message="Encontrei mais de uma possibilidade para o responsavel. Escolha uma opcao para evitar vinculo errado.",
        )

    async def resolve_current_user(
        self,
        *,
        tenant_id: str,
        channel: str,
        provider_user_id: str,
        current_user_name: str | None,
        current_username: str | None,
    ) -> AssigneeResolution:
        link = self._get_link(tenant_id=tenant_id, channel=channel, provider_user_id=provider_user_id)
        if link:
            return AssigneeResolution(
                status="resolved",
                assignee_id=link["board_user_id"],
                display_name=link.get("board_user_name"),
                email=link.get("board_user_email"),
            )

        users = await self._search_users(None, tenant_id=tenant_id, limit=100)
        candidates = [
            user
            for user in users
            if _is_current_user_candidate(user, current_user_name=current_user_name, current_username=current_username)
        ]
        if len(candidates) == 1:
            user = candidates[0]
            self.link_user(
                tenant_id=tenant_id,
                channel=channel,
                provider_user_id=provider_user_id,
                user=user,
                source="auto_current_user",
            )
            return _resolved(user)
        return AssigneeResolution(status="missing")

    def link_user(
        self,
        *,
        tenant_id: str | None,
        channel: str | None,
        provider_user_id: str | None,
        user: dict[str, str | None],
        source: str,
    ) -> None:
        if not self.repository or not tenant_id or not channel or not provider_user_id or not user.get("id"):
            return
        self.repository.upsert_user_identity_link(
            tenant_id=tenant_id,
            channel=channel,
            provider_user_id=provider_user_id,
            board_user_id=str(user["id"]),
            board_user_name=user.get("name"),
            board_user_email=user.get("email"),
            source=source,
        )

    def link_if_current_user(
        self,
        *,
        tenant_id: str | None,
        channel: str | None,
        provider_user_id: str | None,
        user: dict[str, str | None],
        current_user_name: str | None,
        current_username: str | None,
        source: str,
    ) -> None:
        if _is_current_user_candidate(user, current_user_name=current_user_name, current_username=current_username):
            self.link_user(
                tenant_id=tenant_id,
                channel=channel,
                provider_user_id=provider_user_id,
                user=user,
                source=source,
            )

    def _get_link(
        self,
        *,
        tenant_id: str | None,
        channel: str | None,
        provider_user_id: str | None,
    ) -> dict[str, Any] | None:
        if not self.repository or not tenant_id or not channel or not provider_user_id:
            return None
        return self.repository.get_user_identity_link(
            tenant_id=tenant_id,
            channel=channel,
            provider_user_id=provider_user_id,
        )

    async def _search_users(
        self,
        query: str | None,
        *,
        tenant_id: str | None,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, str | None]]:
        if not self.board_tools or not hasattr(self.board_tools, "search_users"):
            return []
        try:
            result = await self.board_tools.search_users(
                tenant_id=tenant_id,
                project_id=project_id,
                query=query,
                limit=limit,
            )
        except TypeError:
            try:
                result = await self.board_tools.search_users(query=query, limit=limit)
            except Exception:
                return []
        except Exception:
            return []
        return _extract_users(result)


def _resolved(user: dict[str, str | None]) -> AssigneeResolution:
    return AssigneeResolution(
        status="resolved",
        assignee_id=user.get("id"),
        display_name=user.get("name") or user.get("email") or user.get("id"),
        email=user.get("email"),
    )


def _extract_users(result: Any) -> list[dict[str, str | None]]:
    items: Any = result
    if isinstance(result, dict):
        items = result.get("users") or result.get("items") or result.get("data") or []
    if not isinstance(items, list):
        return []

    users: list[dict[str, str | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ident = item.get("id") or item.get("user_id") or item.get("uuid")
        if not ident:
            continue
        users.append(
            {
                "id": str(ident),
                "name": _string_or_none(item.get("name") or item.get("full_name") or item.get("username")),
                "email": _string_or_none(item.get("email")),
                "avatarUrl": _string_or_none(item.get("avatarUrl") or item.get("avatar_url")),
            }
        )
    return users


def _matches_exact_user(query: str, user: dict[str, str | None]) -> bool:
    target = _plain(query)
    if not target:
        return False
    values = [
        user.get("name"),
        user.get("email"),
        _email_local_part(user.get("email")),
    ]
    return any(_plain(value) == target for value in values if value)


def _name_represents_user(
    query: str,
    *,
    name: str | None,
    email: str | None,
    username: str | None,
    current_user_name: str | None,
) -> bool:
    target = _plain(query)
    if not target:
        return False
    direct_values = [name, email, _email_local_part(email), current_user_name, username]
    if any(_plain(value) == target for value in direct_values if value):
        return True
    return False


def _is_current_user_candidate(
    user: dict[str, str | None],
    *,
    current_user_name: str | None,
    current_username: str | None,
) -> bool:
    name = user.get("name")
    email = user.get("email")
    values = [current_user_name, current_username]
    user_values = [name, email, _email_local_part(email)]
    for value in values:
        value_plain = _plain(value)
        if value_plain and any(value_plain == _plain(user_value) for user_value in user_values if user_value):
            return True
    name_plain = _plain(name)
    username_plain = _plain(current_username)
    return bool(name_plain and len(name_plain) >= 4 and username_plain and name_plain in username_plain)


def _email_local_part(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    return value.split("@", 1)[0]


def _plain(value: str | None) -> str:
    if not value:
        return ""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def _string_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_slug: str
    user_id: str
    roles: list[str] = field(default_factory=list)
    request_id: str = ""
    correlation_id: str = ""
    channel: str | None = None

    @property
    def user_roles(self) -> list[str]:
        return self.roles

    def has_any_role(self, *roles: str) -> bool:
        return bool(set(self.roles).intersection(roles))

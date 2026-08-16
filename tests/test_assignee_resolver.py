import pytest

from app.application.assignee_resolver import AssigneeResolver


ROGERIO_ID = "9b0dcbc7-e1d9-4c68-8de5-7a314b6d6c8f"
ANA_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class FakeBoardTools:
    users = [
        {"id": ROGERIO_ID, "name": "Rogerio", "email": "rogerio@pmo.local", "avatarUrl": None},
        {"id": ANA_ID, "name": "Ana", "email": "ana@pmo.local", "avatarUrl": None},
    ]

    async def search_users(self, query: str | None = None, limit: int = 20):
        if not query:
            return {"users": self.users[:limit]}
        target = query.casefold().replace("é", "e")
        return {
            "users": [
                user
                for user in self.users
                if target in user["name"].casefold() or target in user["email"].casefold()
            ][:limit]
        }


class FakeRepository:
    def __init__(self):
        self.links = {}

    def get_user_identity_link(self, *, tenant_id, channel, provider_user_id):
        return self.links.get((tenant_id, channel, provider_user_id))

    def upsert_user_identity_link(
        self,
        *,
        tenant_id,
        channel,
        provider_user_id,
        board_user_id,
        board_user_name,
        board_user_email,
        source,
    ):
        link = {
            "tenant_id": tenant_id,
            "channel": channel,
            "provider_user_id": provider_user_id,
            "board_user_id": board_user_id,
            "board_user_name": board_user_name,
            "board_user_email": board_user_email,
            "source": source,
        }
        self.links[(tenant_id, channel, provider_user_id)] = link
        return link


@pytest.mark.asyncio
async def test_resolves_accented_name_to_board_uuid_and_saves_current_user_link():
    repo = FakeRepository()
    resolver = AssigneeResolver(board_tools=FakeBoardTools(), repository=repo)

    result = await resolver.resolve(
        assignee_name="Rogério",
        tenant_id="default",
        channel="telegram",
        provider_user_id="7150117509",
        current_user_name="75099",
        current_username="rogeriomind",
    )

    assert result.status == "resolved"
    assert result.assignee_id == ROGERIO_ID
    assert repo.links[("default", "telegram", "7150117509")]["board_user_id"] == ROGERIO_ID


@pytest.mark.asyncio
async def test_saved_link_does_not_override_different_requested_assignee():
    repo = FakeRepository()
    repo.upsert_user_identity_link(
        tenant_id="default",
        channel="telegram",
        provider_user_id="7150117509",
        board_user_id=ROGERIO_ID,
        board_user_name="Rogerio",
        board_user_email="rogerio@pmo.local",
        source="test",
    )
    resolver = AssigneeResolver(board_tools=FakeBoardTools(), repository=repo)

    result = await resolver.resolve(
        assignee_name="Ana",
        tenant_id="default",
        channel="telegram",
        provider_user_id="7150117509",
        current_user_name="75099",
        current_username="rogeriomind",
    )

    assert result.status == "resolved"
    assert result.assignee_id == ANA_ID


@pytest.mark.asyncio
async def test_resolve_current_user_uses_username_to_persist_link():
    repo = FakeRepository()
    resolver = AssigneeResolver(board_tools=FakeBoardTools(), repository=repo)

    result = await resolver.resolve_current_user(
        tenant_id="default",
        channel="telegram",
        provider_user_id="7150117509",
        current_user_name="75099",
        current_username="rogeriomind",
    )

    assert result.status == "resolved"
    assert result.assignee_id == ROGERIO_ID
    assert repo.links[("default", "telegram", "7150117509")]["source"] == "auto_current_user"

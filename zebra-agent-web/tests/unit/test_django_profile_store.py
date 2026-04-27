"""Integration tests for DjangoProfileStore.

Confirms it satisfies the same contract as InMemoryProfileStore against a real
Django ORM backend.
"""

from __future__ import annotations

import pytest
from zebra_agent.profile import ValuesProfileVersion
from zebra_agent_web.profile_store import DjangoProfileStore


@pytest.fixture
def store() -> DjangoProfileStore:
    return DjangoProfileStore()


@pytest.mark.django_db(transaction=True)
async def test_get_current_returns_none_for_new_user(store: DjangoProfileStore) -> None:
    assert await store.get_current(user_id=42) is None


@pytest.mark.django_db(transaction=True)
async def test_save_version_assigns_id_and_version_number(store: DjangoProfileStore) -> None:
    saved = await store.save_version(
        user_id=1, version=ValuesProfileVersion(core_values_text="honesty")
    )

    assert saved.id != ""
    assert saved.version_number == 1
    assert saved.created_at is not None
    assert saved.core_values_text == "honesty"


@pytest.mark.django_db(transaction=True)
async def test_save_version_increments_monotonically(store: DjangoProfileStore) -> None:
    v1 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="a"))
    v2 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="b"))
    v3 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="c"))

    assert [v1.version_number, v2.version_number, v3.version_number] == [1, 2, 3]


@pytest.mark.django_db(transaction=True)
async def test_get_current_returns_latest_version(store: DjangoProfileStore) -> None:
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="first"))
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="second"))

    current = await store.get_current(user_id=1)

    assert current is not None
    assert current.core_values_text == "second"
    assert current.version_number == 2


@pytest.mark.django_db(transaction=True)
async def test_get_version_returns_specific_old_version(store: DjangoProfileStore) -> None:
    v1 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="first"))
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="second"))

    fetched = await store.get_version(v1.id)

    assert fetched is not None
    assert fetched.id == v1.id
    assert fetched.core_values_text == "first"
    assert fetched.version_number == 1


@pytest.mark.django_db(transaction=True)
async def test_get_version_returns_none_for_unknown_id(store: DjangoProfileStore) -> None:
    assert await store.get_version("does-not-exist") is None


@pytest.mark.django_db(transaction=True)
async def test_users_are_isolated(store: DjangoProfileStore) -> None:
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="user1"))
    await store.save_version(user_id=2, version=ValuesProfileVersion(core_values_text="user2"))
    await store.save_version(user_id=2, version=ValuesProfileVersion(core_values_text="user2 v2"))

    user1 = await store.get_current(user_id=1)
    user2 = await store.get_current(user_id=2)

    assert user1 is not None
    assert user1.core_values_text == "user1"
    assert user1.version_number == 1
    assert user2 is not None
    assert user2.core_values_text == "user2 v2"
    assert user2.version_number == 2


@pytest.mark.django_db(transaction=True)
async def test_versions_are_immutable(store: DjangoProfileStore) -> None:
    v1 = await store.save_version(
        user_id=1, version=ValuesProfileVersion(core_values_text="original")
    )
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="updated"))

    fetched = await store.get_version(v1.id)

    assert fetched is not None
    assert fetched.core_values_text == "original"
    assert fetched.version_number == 1


@pytest.mark.django_db(transaction=True)
async def test_round_trip_with_tags(store: DjangoProfileStore) -> None:
    saved = await store.save_version(
        user_id=1,
        version=ValuesProfileVersion(
            core_values_text="honesty",
            core_values_tags=["honesty", "integrity"],
            deal_breakers_text="no deception",
            deal_breakers_tags=["honesty:hard"],
        ),
    )

    fetched = await store.get_version(saved.id)
    assert fetched is not None
    assert fetched.core_values_tags == ["honesty", "integrity"]
    assert fetched.deal_breakers_tags == ["honesty:hard"]


@pytest.mark.django_db(transaction=True)
async def test_current_version_pointer_updates_on_save(store: DjangoProfileStore) -> None:
    """Confirm save_version updates ValuesProfileModel.current_version atomically."""
    from asgiref.sync import sync_to_async
    from zebra_agent_web.api.models import ValuesProfileModel

    v1 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="first"))

    @sync_to_async
    def _get_pointer() -> str | None:
        return ValuesProfileModel.objects.get(user_id=1).current_version_id

    pointer = await _get_pointer()
    assert pointer == v1.id

    v2 = await store.save_version(
        user_id=1, version=ValuesProfileVersion(core_values_text="second")
    )

    pointer = await _get_pointer()
    assert pointer == v2.id

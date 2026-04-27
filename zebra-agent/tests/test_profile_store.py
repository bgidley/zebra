"""Tests for the in-memory profile store."""

from __future__ import annotations

import pytest

from zebra_agent.profile import ValuesProfileVersion
from zebra_agent.storage.profile import InMemoryProfileStore


@pytest.fixture
def store() -> InMemoryProfileStore:
    return InMemoryProfileStore()


async def test_get_current_returns_none_for_new_user(store: InMemoryProfileStore) -> None:
    assert await store.get_current(user_id=42) is None


async def test_save_version_assigns_id_and_version_number(store: InMemoryProfileStore) -> None:
    draft = ValuesProfileVersion(core_values_text="honesty, growth")

    saved = await store.save_version(user_id=1, version=draft)

    assert saved.id != ""
    assert saved.version_number == 1
    assert saved.created_at is not None
    assert saved.core_values_text == "honesty, growth"


async def test_save_version_increments_monotonically(store: InMemoryProfileStore) -> None:
    v1 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="a"))
    v2 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="b"))
    v3 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="c"))

    assert [v1.version_number, v2.version_number, v3.version_number] == [1, 2, 3]
    assert len({v1.id, v2.id, v3.id}) == 3


async def test_get_current_returns_latest_version(store: InMemoryProfileStore) -> None:
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="first"))
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="second"))

    current = await store.get_current(user_id=1)

    assert current is not None
    assert current.core_values_text == "second"
    assert current.version_number == 2


async def test_get_version_returns_arbitrary_old_version(store: InMemoryProfileStore) -> None:
    v1 = await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="first"))
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="second"))

    fetched = await store.get_version(v1.id)

    assert fetched is not None
    assert fetched.id == v1.id
    assert fetched.core_values_text == "first"
    assert fetched.version_number == 1


async def test_get_version_returns_none_for_unknown_id(store: InMemoryProfileStore) -> None:
    assert await store.get_version("does-not-exist") is None


async def test_users_are_isolated(store: InMemoryProfileStore) -> None:
    await store.save_version(
        user_id=1, version=ValuesProfileVersion(core_values_text="user1 values")
    )
    await store.save_version(
        user_id=2, version=ValuesProfileVersion(core_values_text="user2 values")
    )
    await store.save_version(
        user_id=2, version=ValuesProfileVersion(core_values_text="user2 values v2")
    )

    user1_current = await store.get_current(user_id=1)
    user2_current = await store.get_current(user_id=2)

    assert user1_current is not None
    assert user1_current.core_values_text == "user1 values"
    assert user1_current.version_number == 1

    assert user2_current is not None
    assert user2_current.core_values_text == "user2 values v2"
    assert user2_current.version_number == 2


async def test_versions_are_immutable_after_save(store: InMemoryProfileStore) -> None:
    """Saving a new version must not mutate prior versions."""
    v1 = await store.save_version(
        user_id=1, version=ValuesProfileVersion(core_values_text="original")
    )
    await store.save_version(user_id=1, version=ValuesProfileVersion(core_values_text="updated"))

    fetched_v1 = await store.get_version(v1.id)

    assert fetched_v1 is not None
    assert fetched_v1.core_values_text == "original"
    assert fetched_v1.version_number == 1


async def test_round_trip_through_to_dict(store: InMemoryProfileStore) -> None:
    saved = await store.save_version(
        user_id=1,
        version=ValuesProfileVersion(
            core_values_text="honesty",
            core_values_tags=["honesty", "integrity"],
            deal_breakers_text="no deception",
            deal_breakers_tags=["honesty:hard"],
        ),
    )

    round_tripped = ValuesProfileVersion.from_dict(saved.to_dict())

    assert round_tripped.core_values_text == "honesty"
    assert round_tripped.core_values_tags == ["honesty", "integrity"]
    assert round_tripped.deal_breakers_tags == ["honesty:hard"]
    assert round_tripped.version_number == saved.version_number
    assert round_tripped.id == saved.id

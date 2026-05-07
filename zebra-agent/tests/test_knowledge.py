"""Tests for KnowledgeEntry and InMemoryPersonalKnowledgeStore."""

import pytest

from zebra_agent.knowledge import KNOWLEDGE_CATEGORIES, KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore


# ---------------------------------------------------------------------------
# KnowledgeEntry tests
# ---------------------------------------------------------------------------


def test_create_defaults():
    entry = KnowledgeEntry.create(user_id=1, category="preferences", key="theme", value="dark")
    assert entry.id  # non-empty UUID
    assert entry.user_id == 1
    assert entry.category == "preferences"
    assert entry.key == "theme"
    assert entry.value == "dark"
    assert entry.source == "human"
    assert entry.confidence == 1.0
    assert entry.created_at is not None
    assert entry.last_verified is not None


def test_create_custom_source_and_confidence():
    entry = KnowledgeEntry.create(
        user_id=2, category="facts", key="employer", value="Acme", source="agent", confidence=0.8
    )
    assert entry.source == "agent"
    assert entry.confidence == 0.8


def test_invalid_category_raises():
    with pytest.raises(ValueError, match="Invalid category"):
        KnowledgeEntry.create(user_id=1, category="invalid", key="k", value="v")


def test_confidence_out_of_range_raises():
    with pytest.raises(ValueError, match="confidence"):
        KnowledgeEntry.create(user_id=1, category="facts", key="k", value="v", confidence=1.5)


def test_all_categories_valid():
    for cat in KNOWLEDGE_CATEGORIES:
        entry = KnowledgeEntry.create(user_id=1, category=cat, key="k", value="v")
        assert entry.category == cat


def test_round_trip_serialization():
    entry = KnowledgeEntry.create(user_id=1, category="skills", key="python", value="expert")
    restored = KnowledgeEntry.from_dict(entry.to_dict())
    assert restored.id == entry.id
    assert restored.user_id == entry.user_id
    assert restored.category == entry.category
    assert restored.key == entry.key
    assert restored.value == entry.value
    assert restored.confidence == entry.confidence


# ---------------------------------------------------------------------------
# InMemoryPersonalKnowledgeStore tests
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    return InMemoryPersonalKnowledgeStore()


async def test_add_and_get_entries(store):
    entry = KnowledgeEntry.create(user_id=1, category="preferences", key="lang", value="Python")
    await store.add_entry(entry)
    results = await store.get_entries(user_id=1)
    assert len(results) == 1
    assert results[0].key == "lang"


async def test_get_entries_scoped_to_user(store):
    e1 = KnowledgeEntry.create(user_id=1, category="facts", key="name", value="Alice")
    e2 = KnowledgeEntry.create(user_id=2, category="facts", key="name", value="Bob")
    await store.add_entry(e1)
    await store.add_entry(e2)
    assert len(await store.get_entries(user_id=1)) == 1
    assert len(await store.get_entries(user_id=2)) == 1


async def test_get_entries_filtered_by_category(store):
    await store.add_entry(
        KnowledgeEntry.create(user_id=1, category="preferences", key="k1", value="v1")
    )
    await store.add_entry(KnowledgeEntry.create(user_id=1, category="facts", key="k2", value="v2"))
    prefs = await store.get_entries(user_id=1, category="preferences")
    assert len(prefs) == 1
    assert prefs[0].key == "k1"


async def test_delete_entry(store):
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="k", value="v")
    await store.add_entry(entry)
    deleted = await store.delete_entry(entry.id)
    assert deleted is True
    assert await store.get_entries(user_id=1) == []


async def test_delete_nonexistent_entry(store):
    assert await store.delete_entry("nonexistent-id") is False


async def test_update_entry(store):
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await store.add_entry(entry)
    entry.value = "NewCorp"
    await store.update_entry(entry)
    updated = await store.get_entry(entry.id)
    assert updated is not None
    assert updated.value == "NewCorp"


async def test_get_entry_not_found(store):
    assert await store.get_entry("missing") is None


async def test_context_for_llm_formatted(store):
    await store.add_entry(
        KnowledgeEntry.create(user_id=1, category="preferences", key="theme", value="dark mode")
    )
    await store.add_entry(
        KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="Acme")
    )
    ctx = await store.get_context_for_llm(user_id=1)
    assert "[preferences] theme: dark mode" in ctx
    assert "[facts] employer: Acme" in ctx


async def test_context_for_llm_empty_when_no_entries(store):
    ctx = await store.get_context_for_llm(user_id=42)
    assert ctx == ""


async def test_context_for_llm_user_id_none(store):
    """get_context_for_llm with a non-existent user returns empty string."""
    ctx = await store.get_context_for_llm(user_id=999)
    assert ctx == ""

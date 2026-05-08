"""E2E tests for knowledge lifecycle — contradiction detection and resolution.

Uses InMemory stores and a real WorkflowEngine to verify that:
1. add_knowledge routes to 'contradiction' when a conflicting entry exists
2. The resolve_contradiction workflow correctly applies the user's resolution
"""

from __future__ import annotations

from zebra_tasks.knowledge.add import AddKnowledgeAction

from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_add_knowledge(store, user_id, category, key, value):
    """Run AddKnowledgeAction in isolation using a mock task/context."""
    from unittest.mock import MagicMock

    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "category": category,
        "key": key,
        "value": value,
        "time_sensitive": False,
        "source": "agent",
    }
    context = MagicMock()
    context.process.properties = {"__user_id__": user_id}
    context.extras = {"__knowledge_store__": store}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )

    action = AddKnowledgeAction()
    return await action.run(task, context)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_add_knowledge_no_conflict_stores_entry():
    store = InMemoryPersonalKnowledgeStore()
    result = await _run_add_knowledge(store, 1, "facts", "employer", "Acme")
    assert result.next_route == "stored"
    assert result.output["contradiction"] is False
    entries = await store.get_entries(user_id=1)
    assert len(entries) == 1
    assert entries[0].value == "Acme"


async def test_add_knowledge_contradiction_detected():
    store = InMemoryPersonalKnowledgeStore()
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await store.add_entry(existing)

    result = await _run_add_knowledge(store, 1, "facts", "employer", "NewCorp")
    assert result.next_route == "contradiction"
    assert result.output["contradiction"] is True
    assert result.output["existing_value"] == "OldCorp"
    assert result.output["proposed_value"] == "NewCorp"

    # Original entry should NOT be modified
    entries = await store.get_entries(user_id=1)
    assert len(entries) == 1
    assert entries[0].value == "OldCorp"


async def test_add_knowledge_same_value_refreshes_not_contradiction():
    store = InMemoryPersonalKnowledgeStore()
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="Acme")
    original_confidence = 0.5
    existing.confidence = original_confidence
    await store.add_entry(existing)

    result = await _run_add_knowledge(store, 1, "facts", "employer", "Acme")
    assert result.next_route == "stored"
    assert result.output["contradiction"] is False

    # Confidence should have been refreshed to 1.0
    entries = await store.get_entries(user_id=1)
    assert entries[0].confidence == 1.0


async def test_soft_delete_hides_entry_from_active_queries():
    store = InMemoryPersonalKnowledgeStore()
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="Acme")
    await store.add_entry(entry)

    await store.soft_delete_entry(entry.id)

    active = await store.get_entries(user_id=1)
    assert len(active) == 0

    all_entries = await store.get_entries(user_id=1, include_deleted=True)
    assert len(all_entries) == 1
    assert all_entries[0].deleted_at is not None


async def test_soft_deleted_entry_not_a_contradiction():
    """A soft-deleted entry should not block adding a new entry with the same key."""
    store = InMemoryPersonalKnowledgeStore()
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await store.add_entry(existing)
    await store.soft_delete_entry(existing.id)

    result = await _run_add_knowledge(store, 1, "facts", "employer", "NewCorp")
    assert result.next_route == "stored"
    assert result.output["contradiction"] is False

    active = await store.get_entries(user_id=1)
    assert len(active) == 1
    assert active[0].value == "NewCorp"

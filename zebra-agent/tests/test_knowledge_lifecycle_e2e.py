"""E2E tests for knowledge lifecycle — contradiction detection and resolution.

Uses InMemory stores and a real WorkflowEngine to verify that:
1. add_knowledge routes to 'contradiction' when a conflicting entry exists
2. The resolve_contradiction workflow correctly applies the user's resolution
"""

from __future__ import annotations

from pathlib import Path

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.knowledge.add import AddKnowledgeAction
from zebra_tasks.knowledge.apply_resolution import ApplyResolutionAction

from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"


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


def _make_resolve_registry(knowledge_store):
    """Build a registry and engine for resolve_contradiction workflow tests."""
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("apply_resolution", ApplyResolutionAction)

    engine_store = InMemoryStore()
    engine = WorkflowEngine(engine_store, registry, extras={"__knowledge_store__": knowledge_store})
    return engine, engine_store


async def _load_resolve_definition():
    yaml_text = (WORKFLOWS_DIR / "resolve_contradiction.yaml").read_text()
    return load_definition_from_yaml(yaml_text)


# ---------------------------------------------------------------------------
# Action-level tests (no engine)
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


# ---------------------------------------------------------------------------
# Workflow-level E2E tests — contradiction → resolve_contradiction workflow
# ---------------------------------------------------------------------------


async def test_contradiction_triggers_resolve_workflow_keep_existing():
    """Contradicting entry detection → resolve_contradiction workflow → keep_existing."""
    knowledge_store = InMemoryPersonalKnowledgeStore()
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await knowledge_store.add_entry(existing)

    # Step 1: add_knowledge detects contradiction
    add_result = await _run_add_knowledge(knowledge_store, 1, "facts", "employer", "NewCorp")
    assert add_result.next_route == "contradiction"

    # Step 2: Launch resolve_contradiction workflow with contradiction details
    engine, engine_store = _make_resolve_registry(knowledge_store)
    definition = await _load_resolve_definition()

    process = await engine.create_process(
        definition,
        properties={
            "__user_id__": 1,
            "entry_id": add_result.output["entry_id"],
            "existing_value": add_result.output["existing_value"],
            "proposed_value": add_result.output["proposed_value"],
            "category": "facts",
            "key": "employer",
        },
    )
    await engine.start_process(process.id)

    # Workflow should be waiting on the human task
    pending = await engine.get_pending_tasks(process.id)
    assert len(pending) == 1
    assert pending[0].task_definition_id == "present_contradiction"

    # Step 3: User chooses to keep existing
    await engine.complete_task(
        pending[0].id,
        TaskResult.ok(output={"resolution": "keep_existing"}),
    )

    process = await engine_store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE

    # Entry should be unchanged
    entries = await knowledge_store.get_entries(user_id=1)
    assert len(entries) == 1
    assert entries[0].value == "OldCorp"


async def test_contradiction_resolve_workflow_use_new():
    """resolve_contradiction with 'use_new' updates the entry to the proposed value."""
    knowledge_store = InMemoryPersonalKnowledgeStore()
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await knowledge_store.add_entry(existing)

    add_result = await _run_add_knowledge(knowledge_store, 1, "facts", "employer", "NewCorp")
    assert add_result.next_route == "contradiction"

    engine, engine_store = _make_resolve_registry(knowledge_store)
    definition = await _load_resolve_definition()

    process = await engine.create_process(
        definition,
        properties={
            "__user_id__": 1,
            "entry_id": add_result.output["entry_id"],
            "existing_value": add_result.output["existing_value"],
            "proposed_value": add_result.output["proposed_value"],
            "category": "facts",
            "key": "employer",
        },
    )
    await engine.start_process(process.id)

    pending = await engine.get_pending_tasks(process.id)
    await engine.complete_task(
        pending[0].id,
        TaskResult.ok(output={"resolution": "use_new"}),
    )

    process = await engine_store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE

    # Entry should be updated to NewCorp
    entries = await knowledge_store.get_entries(user_id=1)
    assert len(entries) == 1
    assert entries[0].value == "NewCorp"
    assert entries[0].confidence == 1.0


async def test_contradiction_resolve_workflow_keep_both():
    """resolve_contradiction with 'keep_both' adds a second entry with _alt suffix."""
    knowledge_store = InMemoryPersonalKnowledgeStore()
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await knowledge_store.add_entry(existing)

    add_result = await _run_add_knowledge(knowledge_store, 1, "facts", "employer", "NewCorp")
    assert add_result.next_route == "contradiction"

    engine, engine_store = _make_resolve_registry(knowledge_store)
    definition = await _load_resolve_definition()

    process = await engine.create_process(
        definition,
        properties={
            "__user_id__": 1,
            "entry_id": add_result.output["entry_id"],
            "existing_value": add_result.output["existing_value"],
            "proposed_value": add_result.output["proposed_value"],
            "category": "facts",
            "key": "employer",
        },
    )
    await engine.start_process(process.id)

    pending = await engine.get_pending_tasks(process.id)
    await engine.complete_task(
        pending[0].id,
        TaskResult.ok(output={"resolution": "keep_both"}),
    )

    process = await engine_store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE

    # Both entries should exist: original + new alt
    entries = await knowledge_store.get_entries(user_id=1)
    assert len(entries) == 2
    values = {e.value for e in entries}
    assert "OldCorp" in values
    assert "NewCorp" in values
    keys = {e.key for e in entries}
    assert "employer" in keys
    assert "employer_alt" in keys

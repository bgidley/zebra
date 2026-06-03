"""Unit tests for ApplyResolutionAction."""

from unittest.mock import MagicMock

from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore

from zebra_tasks.knowledge.apply_resolution import ApplyResolutionAction


def _make_context(store, process_props, task_output):
    context = MagicMock()
    context.extras = {"__knowledge_store__": store}
    context.process.properties = process_props
    context.get_process_property = MagicMock(side_effect=lambda k, d=None: process_props.get(k, d))
    context.get_task_output = MagicMock(
        side_effect=lambda k: task_output if k == "present_contradiction" else None
    )
    return context


def _employer_props(entry_id, proposed="NewCorp", category="facts", key="employer"):
    return {
        "__user_id__": 1,
        "entry_id": entry_id,
        "proposed_value": proposed,
        "category": category,
        "key": key,
    }


async def test_no_store_degrades_gracefully():
    context = MagicMock()
    context.extras = {}
    result = await ApplyResolutionAction().run(MagicMock(), context)
    assert result.success
    assert result.output["resolution"] == "skipped"


async def test_no_task_output_degrades_gracefully():
    store = InMemoryPersonalKnowledgeStore()
    context = MagicMock()
    context.extras = {"__knowledge_store__": store}
    context.get_task_output = MagicMock(return_value=None)
    result = await ApplyResolutionAction().run(MagicMock(), context)
    assert result.output["resolution"] == "skipped"


async def test_keep_existing_does_not_modify_store():
    store = InMemoryPersonalKnowledgeStore()
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await store.add_entry(entry)

    context = _make_context(store, _employer_props(entry.id), {"resolution": "keep_existing"})
    result = await ApplyResolutionAction().run(MagicMock(), context)

    assert result.output["resolution"] == "kept_existing"
    entries = await store.get_entries(user_id=1)
    assert entries[0].value == "OldCorp"


async def test_use_new_updates_entry_value():
    store = InMemoryPersonalKnowledgeStore()
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    entry.confidence = 0.5
    await store.add_entry(entry)

    context = _make_context(store, _employer_props(entry.id), {"resolution": "use_new"})
    result = await ApplyResolutionAction().run(MagicMock(), context)

    assert result.output["resolution"] == "updated"
    updated = await store.get_entry(entry.id)
    assert updated.value == "NewCorp"
    assert updated.confidence == 1.0


async def test_keep_both_adds_alt_entry():
    store = InMemoryPersonalKnowledgeStore()
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    await store.add_entry(entry)

    context = _make_context(store, _employer_props(entry.id), {"resolution": "keep_both"})
    result = await ApplyResolutionAction().run(MagicMock(), context)

    assert result.output["resolution"] == "kept_both"
    entries = await store.get_entries(user_id=1)
    assert len(entries) == 2
    keys = {e.key for e in entries}
    assert "employer" in keys
    assert "employer_alt" in keys
    values = {e.value for e in entries}
    assert "OldCorp" in values
    assert "NewCorp" in values


async def test_unknown_resolution_returns_skipped():
    store = InMemoryPersonalKnowledgeStore()
    entry = KnowledgeEntry.create(user_id=1, category="facts", key="k", value="v")
    await store.add_entry(entry)

    context = _make_context(
        store,
        _employer_props(entry.id, proposed="v2", key="k"),
        {"resolution": "do_something_weird"},
    )
    result = await ApplyResolutionAction().run(MagicMock(), context)
    assert result.output["resolution"] == "skipped"

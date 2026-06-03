"""Tests for AddKnowledgeAction."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.knowledge import KnowledgeEntry

from zebra_tasks.knowledge.add import AddKnowledgeAction


@pytest.fixture
def action():
    return AddKnowledgeAction()


def _make_context(user_id=1, extras=None):
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {"__user_id__": user_id}
    context.extras = extras or {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    return context


def _make_task(category="facts", key="employer", value="Acme", time_sensitive=False):
    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "category": category,
        "key": key,
        "value": value,
        "time_sensitive": time_sensitive,
        "source": "agent",
    }
    return task


def _make_store(existing=None):
    store = MagicMock()
    store.find_contradicting_entry = AsyncMock(return_value=existing)
    store.add_entry = AsyncMock()
    store.update_entry = AsyncMock()
    return store


async def test_no_store_returns_stored_route(action):
    context = _make_context(extras={})
    result = await action.run(_make_task(), context)
    assert result.output["contradiction"] is False
    assert result.next_route == "stored"


async def test_no_user_id_returns_stored_route(action):
    context = _make_context(user_id=None, extras={"__knowledge_store__": _make_store()})
    context.process.properties = {}
    result = await action.run(_make_task(), context)
    assert result.next_route == "stored"


async def test_new_entry_stored(action):
    store = _make_store(existing=None)
    context = _make_context(extras={"__knowledge_store__": store})
    result = await action.run(_make_task(), context)
    assert result.next_route == "stored"
    assert result.output["contradiction"] is False
    store.add_entry.assert_called_once()


async def test_same_value_refreshes_existing(action):
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="Acme")
    store = _make_store(existing=existing)
    context = _make_context(extras={"__knowledge_store__": store})
    result = await action.run(_make_task(value="Acme"), context)
    assert result.next_route == "stored"
    assert result.output["contradiction"] is False
    store.update_entry.assert_called_once()
    store.add_entry.assert_not_called()


async def test_different_value_triggers_contradiction(action):
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    store = _make_store(existing=existing)
    context = _make_context(extras={"__knowledge_store__": store})
    result = await action.run(_make_task(value="NewCorp"), context)
    assert result.next_route == "contradiction"
    assert result.output["contradiction"] is True
    assert result.output["existing_value"] == "OldCorp"
    assert result.output["proposed_value"] == "NewCorp"
    store.add_entry.assert_not_called()
    store.update_entry.assert_not_called()

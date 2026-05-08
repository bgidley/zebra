"""Tests for PickEntriesForVerificationAction."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.knowledge import KnowledgeEntry

from zebra_tasks.knowledge.verify import PickEntriesForVerificationAction


@pytest.fixture
def action():
    return PickEntriesForVerificationAction()


def _make_context(user_id=1, extras=None):
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {"__user_id__": user_id}
    context.extras = extras or {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock()
    return context


def _make_task(props=None):
    task = MagicMock()
    task.id = "task-1"
    task.properties = props or {}
    return task


def _make_store(entries):
    store = MagicMock()
    store.get_entries_for_verification = AsyncMock(return_value=entries)
    return store


async def test_no_store_returns_empty(action):
    context = _make_context(extras={})
    result = await action.run(_make_task(), context)
    assert result.output == {"entries": [], "count": 0}


async def test_no_user_id_returns_empty(action):
    context = _make_context(extras={"__knowledge_store__": _make_store([])})
    context.process.properties = {}
    result = await action.run(_make_task(), context)
    assert result.output == {"entries": [], "count": 0}


async def test_returns_serialized_entries(action):
    entries = [
        KnowledgeEntry.create(
            user_id=1, category="facts", key="employer", value="Acme", confidence=0.4
        ),
        KnowledgeEntry.create(
            user_id=1, category="preferences", key="theme", value="dark", confidence=0.5
        ),
    ]
    store = _make_store(entries)
    context = _make_context(extras={"__knowledge_store__": store})
    result = await action.run(_make_task(), context)
    assert result.output["count"] == 2
    assert len(result.output["entries"]) == 2
    assert result.output["entries"][0]["key"] == "employer"
    assert "last_verified" in result.output["entries"][0]


async def test_passes_params_to_store(action):
    store = _make_store([])
    context = _make_context(extras={"__knowledge_store__": store})
    props = {"low_confidence_threshold": 0.7, "max_age_days": 30, "max_entries": 3}
    await action.run(_make_task(props), context)
    store.get_entries_for_verification.assert_called_once_with(
        user_id=1, low_confidence_threshold=0.7, max_age_days=30, max_entries=3
    )


async def test_empty_store_returns_empty(action):
    store = _make_store([])
    context = _make_context(extras={"__knowledge_store__": store})
    result = await action.run(_make_task(), context)
    assert result.output == {"entries": [], "count": 0}

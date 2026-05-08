"""Tests for DecayConfidenceAction."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.knowledge import KnowledgeEntry

from zebra_tasks.knowledge.decay import DecayConfidenceAction


@pytest.fixture
def action():
    return DecayConfidenceAction()


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {"__user_id__": 1}
    context.extras = {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    return context


def _make_task(props=None):
    task = MagicMock()
    task.id = "task-1"
    task.properties = props or {}
    return task


def _make_store(entries):
    store = MagicMock()
    store.get_entries = AsyncMock(return_value=entries)
    store.update_entry = AsyncMock()
    return store


def _aged_entry(category, confidence=1.0, days=400, time_sensitive=True):
    e = KnowledgeEntry.create(
        user_id=1,
        category=category,
        key="k",
        value="v",
        confidence=confidence,
        time_sensitive=time_sensitive,
    )
    e.last_verified = datetime.now(UTC) - timedelta(days=days)
    return e


async def test_no_store_returns_zero(action, mock_context):
    result = await action.run(_make_task(), mock_context)
    assert result.output == {"decayed": 0, "skipped": 0}


async def test_no_user_id_returns_zero(action, mock_context):
    mock_context.process.properties = {}
    result = await action.run(_make_task(), mock_context)
    assert result.output == {"decayed": 0, "skipped": 0}


async def test_non_time_sensitive_skipped(action, mock_context):
    entry = _aged_entry("facts", time_sensitive=False)
    store = _make_store([entry])
    mock_context.extras["__knowledge_store__"] = store
    result = await action.run(_make_task(), mock_context)
    assert result.output["decayed"] == 0
    assert result.output["skipped"] == 1
    store.update_entry.assert_not_called()


async def test_history_category_skipped(action, mock_context):
    entry = _aged_entry("history", time_sensitive=True)
    store = _make_store([entry])
    mock_context.extras["__knowledge_store__"] = store
    result = await action.run(_make_task(), mock_context)
    assert result.output["decayed"] == 0
    assert result.output["skipped"] == 1


async def test_time_sensitive_entry_decayed(action, mock_context):
    # facts half-life = 365 days; after 365 days confidence should halve
    entry = _aged_entry("facts", confidence=1.0, days=365, time_sensitive=True)
    store = _make_store([entry])
    mock_context.extras["__knowledge_store__"] = store
    result = await action.run(_make_task(), mock_context)
    assert result.output["decayed"] == 1
    store.update_entry.assert_called_once()
    updated = store.update_entry.call_args[0][0]
    assert 0.45 < updated.confidence < 0.55


async def test_confidence_not_below_floor(action, mock_context):
    entry = _aged_entry("routines", confidence=0.11, days=1000, time_sensitive=True)
    store = _make_store([entry])
    mock_context.extras["__knowledge_store__"] = store
    result = await action.run(_make_task(), mock_context)
    assert result.output["decayed"] == 1
    updated = store.update_entry.call_args[0][0]
    assert updated.confidence >= 0.1

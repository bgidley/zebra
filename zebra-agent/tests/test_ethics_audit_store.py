"""Tests for InMemoryEthicsAuditStore."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from zebra_agent.storage.ethics_audit import InMemoryEthicsAuditStore
from zebra_agent.storage.interfaces import EthicsAuditEntry


def _entry(**kwargs) -> EthicsAuditEntry:
    defaults = {
        "process_id": "proc-1",
        "goal": "help me do something",
        "approved": True,
        "overall_reasoning": "Passes all three Kantian tests",
        "check_type": "kantian",
    }
    defaults.update(kwargs)
    return EthicsAuditEntry(**defaults)


@pytest.fixture
def store() -> InMemoryEthicsAuditStore:
    return InMemoryEthicsAuditStore()


async def test_initialize(store):
    await store.initialize()
    assert store._initialized


async def test_append_and_get(store):
    await store.initialize()
    entry = _entry()
    await store.append(entry)
    fetched = await store.get(entry.id)
    assert fetched is entry


async def test_get_missing_returns_none(store):
    await store.initialize()
    assert await store.get("does-not-exist") is None


async def test_list_all(store):
    await store.initialize()
    e1 = _entry(goal="first")
    e2 = _entry(goal="second")
    await store.append(e1)
    await store.append(e2)
    results = await store.list_entries()
    assert len(results) == 2


async def test_list_ordered_newest_first(store):
    await store.initialize()
    now = datetime.now(UTC)
    old = _entry(evaluated_at=now - timedelta(hours=1))
    new = _entry(evaluated_at=now)
    await store.append(old)
    await store.append(new)
    results = await store.list_entries()
    assert results[0].id == new.id
    assert results[1].id == old.id


async def test_filter_by_approved(store):
    await store.initialize()
    yes = _entry(approved=True)
    no = _entry(approved=False)
    await store.append(yes)
    await store.append(no)

    approved = await store.list_entries(approved=True)
    assert all(e.approved for e in approved)

    rejected = await store.list_entries(approved=False)
    assert all(not e.approved for e in rejected)


async def test_filter_by_process_id(store):
    await store.initialize()
    e1 = _entry(process_id="proc-A")
    e2 = _entry(process_id="proc-B")
    await store.append(e1)
    await store.append(e2)
    results = await store.list_entries(process_id="proc-A")
    assert len(results) == 1
    assert results[0].process_id == "proc-A"


async def test_filter_by_date_range(store):
    await store.initialize()
    now = datetime.now(UTC)
    yesterday = _entry(evaluated_at=now - timedelta(days=1))
    today = _entry(evaluated_at=now)
    await store.append(yesterday)
    await store.append(today)

    cutoff = now - timedelta(hours=1)
    results = await store.list_entries(from_date=cutoff)
    assert len(results) == 1
    assert results[0].id == today.id


async def test_pagination(store):
    await store.initialize()
    for i in range(5):
        await store.append(_entry(goal=f"goal-{i}"))
    page1 = await store.list_entries(limit=2, offset=0)
    page2 = await store.list_entries(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {e.id for e in page1}.isdisjoint({e.id for e in page2})


async def test_immutability_no_delete_or_update_methods(store):
    """EthicsAuditStore exposes no delete or update methods."""
    assert not hasattr(store, "delete")
    assert not hasattr(store, "update")
    assert not hasattr(store, "remove")

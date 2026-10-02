"""Tests for the dashboard Running Activities panel (#126)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra_agent_web.api import agent_engine, engine
from zebra_agent_web.api.web_views import _running_activities


class _StubLibrary:
    async def list_workflows(self):
        return []


class _StubMetrics:
    async def get_all_stats(self):
        return []

    async def get_recent_runs(self, limit=10):
        return []


def _definition(def_id: str, tasks: dict[str, bool]) -> ProcessDefinition:
    """Build a definition whose tasks map id -> auto flag."""
    return ProcessDefinition(
        id=def_id,
        name=def_id,
        first_task_id=next(iter(tasks)),
        tasks={
            tid: TaskDefinition(id=tid, name=f"{tid.title()} Step", auto=auto)
            for tid, auto in tasks.items()
        },
    )


async def _process(store, pid, def_id, state=ProcessState.RUNNING, parent=None, **props):
    process = ProcessInstance(
        id=pid,
        definition_id=def_id,
        state=state,
        parent_process_id=parent,
        properties=props,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    await store.save_process(process)
    return process


async def _task(store, tid, pid, def_tid, state):
    await store.save_task(
        TaskInstance(id=tid, process_id=pid, task_definition_id=def_tid, state=state, foe_id="f")
    )


@pytest.fixture
async def store():
    s = InMemoryStore()
    await s.save_definition(_definition("agent_main", {"execute": True}))
    await s.save_definition(_definition("child_wf", {"draft": True, "review": False}))
    return s


async def test_no_running_processes_returns_empty(store):
    await _process(store, "done", "agent_main", state=ProcessState.COMPLETE, goal="old")

    assert await _running_activities(store) == []


async def test_running_goal_reports_goal_tasks_and_cost(store):
    await _process(
        store,
        "root",
        "agent_main",
        goal="Write a haiku",
        run_id="run-1",
        __workflow_name__="Poetry",
        __total_cost__=0.0123,
    )
    await _task(store, "t1", "root", "execute", TaskState.RUNNING)
    await _task(store, "t0", "root", "execute", TaskState.COMPLETE)

    [activity] = await _running_activities(store)

    assert activity["goal"] == "Write a haiku"
    assert activity["run_id"] == "run-1"
    assert activity["workflow_name"] == "Poetry"
    assert activity["cost"] == pytest.approx(0.0123)
    assert activity["current_tasks"] == ["Execute Step"]
    assert activity["awaiting_human"] is False


async def test_child_human_task_flags_root_goal(store):
    await _process(store, "root", "agent_main", goal="Plan trip", run_id="run-2")
    await _process(store, "child", "child_wf", parent="root")
    await _task(store, "t1", "root", "execute", TaskState.RUNNING)
    await _task(store, "t2", "child", "review", TaskState.READY)

    activities = await _running_activities(store)

    assert len(activities) == 1  # child is folded under its root, not listed separately
    [activity] = activities
    assert activity["awaiting_human"] is True
    assert activity["human_task_id"] == "t2"
    assert activity["current_tasks"] == ["Execute Step", "Review Step"]


async def test_running_child_of_finished_parent_is_not_listed(store):
    await _process(store, "root", "agent_main", state=ProcessState.COMPLETE, goal="x")
    await _process(store, "child", "child_wf", parent="root")

    assert await _running_activities(store) == []


async def test_limit_caps_results(store):
    for i in range(3):
        await _process(store, f"p{i}", "agent_main", goal=f"goal {i}")

    assert len(await _running_activities(store, limit=2)) == 2


# ---------------------------------------------------------------------------
# Rendered dashboard
# ---------------------------------------------------------------------------


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def stub_engines(monkeypatch, store, completed_setup):
    async def _noop():
        return None

    def _raise_runtime():
        raise RuntimeError("not initialized in tests")

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_library", lambda: _StubLibrary())
    monkeypatch.setattr(agent_engine, "get_metrics", lambda: _StubMetrics())
    monkeypatch.setattr(agent_engine, "get_budget_manager", _raise_runtime)
    monkeypatch.setattr(agent_engine, "get_trust", _raise_runtime)
    monkeypatch.setattr(engine, "ensure_initialized", _noop)
    monkeypatch.setattr(engine, "get_store", lambda: store)
    return store


@pytest.mark.django_db(transaction=True)
async def test_dashboard_renders_running_activity(authenticated_async_client, stub_engines):
    await _process(stub_engines, "root", "agent_main", goal="Summarise inbox", run_id="run-9")
    await _process(stub_engines, "child", "child_wf", parent="root")
    await _task(stub_engines, "human-1", "child", "review", TaskState.READY)

    response = await authenticated_async_client.get("/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Running Activities" in html
    assert "Summarise inbox" in html
    assert "/runs/run-9/" in html
    assert "/tasks/human-1/" in html
    assert "awaiting input" in html


@pytest.mark.django_db(transaction=True)
async def test_dashboard_survives_store_failure(
    authenticated_async_client, stub_engines, monkeypatch
):
    async def _boom():
        raise RuntimeError("store down")

    monkeypatch.setattr(stub_engines, "get_running_processes", _boom)

    response = await authenticated_async_client.get("/")

    assert response.status_code == 200
    assert "Nothing running" in response.content.decode()


@pytest.mark.django_db(transaction=True)
async def test_dashboard_shows_empty_state(authenticated_async_client, stub_engines):
    response = await authenticated_async_client.get("/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Running Activities" in html
    assert "Nothing running" in html

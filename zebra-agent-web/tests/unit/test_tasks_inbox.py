"""Tests for the Tasks inbox (#217): read model, /tasks/ page, badge and dashboard agreeing."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from zebra.core.engine import MANUAL_REVIEW_FLAG
from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra_agent_web.api import engine
from zebra_agent_web.api.inbox import inbox_items

NOW = datetime.now(UTC)


def _definition() -> ProcessDefinition:
    return ProcessDefinition(
        id="wf",
        name="Weekly Digest",
        first_task_id="work",
        tasks={
            "work": TaskDefinition(id="work", name="Do Work", auto=True),
            "ask": TaskDefinition(
                id="ask",
                name="Approve Digest",
                auto=False,
                properties={"schema": {"type": "object", "title": "Approve the digest"}},
            ),
            "send": TaskDefinition(id="send", name="Send Email", auto=True),
            # Completed by the host builder, not a person (#98)
            "await_build": TaskDefinition(
                id="await_build",
                name="Claude Code Is Building",
                auto=False,
                properties={"external": "builder"},
            ),  # fmt: skip
        },
    )


async def _process(
    store,
    pid: str,
    *,
    state: ProcessState = ProcessState.RUNNING,
    parent: str | None = None,
    props: dict | None = None,
) -> None:
    if props is None:
        props = {"goal": f"goal {pid}", "run_id": f"r-{pid}"}
    await store.save_process(
        ProcessInstance(
            id=pid,
            definition_id="wf",
            state=state,
            parent_process_id=parent,
            properties=props,
            created_at=NOW - timedelta(hours=2),
        )
    )


async def _task(
    store,
    tid: str,
    pid: str,
    task_def: str,
    state: TaskState = TaskState.READY,
    *,
    age_minutes: int = 10,
    flagged: bool = False,
) -> None:
    await store.save_task(
        TaskInstance(
            id=tid,
            process_id=pid,
            task_definition_id=task_def,
            state=state,
            foe_id="f",
            properties={MANUAL_REVIEW_FLAG: True} if flagged else {},
            created_at=NOW - timedelta(minutes=age_minutes),
            updated_at=NOW - timedelta(minutes=age_minutes),
        )
    )


@pytest.fixture
async def store():
    s = InMemoryStore()
    await s.save_definition(_definition())
    return s


async def _mixed(store) -> None:
    """Two waiting human tasks, one review-flagged task, and things that must not show."""
    await _process(store, "a")
    await _task(store, "ht-old", "a", "ask", age_minutes=60)
    await _process(store, "b")
    await _task(store, "ht-new", "b", "ask", age_minutes=5)
    await _process(store, "c")
    await _task(store, "rv-1", "c", "send", TaskState.RUNNING, age_minutes=30, flagged=True)
    # Running normally: an auto task in flight
    await _process(store, "d")
    await _task(store, "auto-1", "d", "work", TaskState.RUNNING)
    # Leftover READY human tasks on finished processes
    await _process(store, "done", state=ProcessState.COMPLETE)
    await _task(store, "stale-1", "done", "ask")
    await _process(store, "dead", state=ProcessState.FAILED)
    await _task(store, "stale-2", "dead", "ask")
    # Parked on an external wait: nothing for a person to do
    await _process(store, "e")
    await _task(store, "ext-1", "e", "await_build")


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------


async def test_lists_only_waiting_items_oldest_first(store):
    await _mixed(store)

    items = await inbox_items(store)

    assert [i["id"] for i in items] == ["ht-old", "rv-1", "ht-new"]
    assert [i["kind"] for i in items] == ["human", "review", "human"]


async def test_human_item_fields(store):
    await _process(store, "a")
    await _task(store, "ht-1", "a", "ask")

    [item] = await inbox_items(store)

    assert item["task_name"] == "Approve Digest"
    assert item["title"] == "Approve the digest"
    assert item["goal"] == "goal a"
    assert item["run_id"] == "r-a"
    assert item["root_process_id"] == "a"
    assert item["workflow_name"] == "Weekly Digest"


async def test_review_item_fields(store):
    await _process(store, "c")
    await _task(store, "rv-1", "c", "send", TaskState.RUNNING, flagged=True)

    [item] = await inbox_items(store)

    assert item["kind"] == "review"
    assert item["task_name"] == "Send Email"
    assert item["execution_attempt"] == 0
    assert item["goal"] == "goal c"


async def test_subprocess_task_takes_goal_and_run_from_root(store):
    await _process(
        store, "root", props={"goal": "Plan the trip", "run_id": "r-1", "__workflow_name__": "Trip"}
    )
    await _process(store, "child", parent="root", props={})
    await _task(store, "ht-1", "child", "ask")

    [item] = await inbox_items(store)

    assert item["process_id"] == "child"
    assert item["root_process_id"] == "root"
    assert (item["goal"], item["run_id"], item["workflow_name"]) == ("Plan the trip", "r-1", "Trip")


async def test_waiting_process_without_run_record_is_listed(store):
    """The agent run is over (no in-progress record) but the process still waits on you."""
    await _process(store, "a", props={"goal": "Bug report"})
    await _task(store, "ht-1", "a", "ask")

    [item] = await inbox_items(store)

    assert item["run_id"] is None
    assert item["goal"] == "Bug report"


async def test_tasks_on_finished_processes_are_skipped(store):
    await _process(store, "done", state=ProcessState.COMPLETE)
    await _task(store, "stale", "done", "ask")

    assert await inbox_items(store) == []


async def test_ready_auto_task_is_skipped(store):
    """A READY auto task is about to run, not waiting on a person (#218)."""
    await _process(store, "a")
    await _task(store, "auto-ready", "a", "work", TaskState.READY)

    assert await inbox_items(store) == []


async def test_task_with_unknown_definition_is_skipped(store):
    await _process(store, "a")
    await _task(store, "ghost", "a", "no_such_task")

    assert await inbox_items(store) == []


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def stub_store(monkeypatch, completed_setup, store):
    async def _noop():
        return None

    monkeypatch.setattr(engine, "ensure_initialized", _noop)
    monkeypatch.setattr(engine, "get_store", lambda: store)
    return store


@pytest.mark.django_db(transaction=True)
async def test_tasks_page_renders_inbox_not_redirect(authenticated_async_client, stub_store):
    await _mixed(stub_store)

    response = await authenticated_async_client.get("/tasks/")

    assert response.status_code == 200
    assert "pages/tasks_inbox.html" in [t.name for t in response.templates]
    html = response.content.decode()
    rows = re.findall(r'data-inbox-item="([^"]+)" data-kind="([^"]+)"', html)
    assert rows == [("ht-old", "human"), ("rv-1", "review"), ("ht-new", "human")]
    assert 'href="/tasks/ht-old/"' in html
    assert 'hx-post="/tasks/rv-1/retry/"' in html and 'hx-post="/tasks/rv-1/fail/"' in html
    assert 'href="/runs/r-a/"' in html
    for absent in ("auto-1", "stale-1", "stale-2", "goal d"):
        assert absent not in html


@pytest.mark.django_db(transaction=True)
async def test_goal_links_to_trace_without_run(authenticated_async_client, stub_store):
    await _process(stub_store, "a", props={"goal": "Bug report"})
    await _task(stub_store, "ht-1", "a", "ask")

    html = (await authenticated_async_client.get("/tasks/")).content.decode()

    assert 'href="/processes/a/trace/"' in html


@pytest.mark.django_db(transaction=True)
async def test_tasks_page_empty_state(authenticated_async_client, stub_store):
    response = await authenticated_async_client.get("/tasks/")

    assert response.status_code == 200
    assert 'data-testid="inbox-empty"' in response.content.decode()


@pytest.mark.django_db(transaction=True)
async def test_tasks_page_store_failure(authenticated_async_client, completed_setup, monkeypatch):
    async def _boom():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(engine, "ensure_initialized", _boom)

    response = await authenticated_async_client.get("/tasks/")

    assert response.status_code == 200
    assert 'data-testid="inbox-error"' in response.content.decode()


class _StubLibrary:
    async def list_workflows(self):
        return []


class _StubMetrics:
    async def get_all_stats(self):
        return []

    async def get_recent_runs(self, limit=10):
        return []


@pytest.fixture
def stub_dashboard(monkeypatch, stub_store):
    from zebra_agent_web.api import agent_engine

    async def _noop():
        return None

    def _not_ready():
        raise RuntimeError("not initialized in tests")

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_library", lambda: _StubLibrary())
    monkeypatch.setattr(agent_engine, "get_metrics", lambda: _StubMetrics())
    monkeypatch.setattr(agent_engine, "get_budget_manager", _not_ready)
    monkeypatch.setattr(agent_engine, "get_trust", _not_ready)
    return stub_store


@pytest.mark.django_db(transaction=True)
async def test_badge_dashboard_and_inbox_agree(authenticated_async_client, stub_dashboard):
    await _mixed(stub_dashboard)

    inbox = (await authenticated_async_client.get("/tasks/")).content.decode()
    badge = (await authenticated_async_client.get("/nav/needs-you/")).content.decode()
    home = (await authenticated_async_client.get("/")).content.decode()

    rows = re.findall(r'data-inbox-item="([^"]+)" data-kind="([^"]+)"', inbox)
    strip = home.split('data-testid="needs-you"', 1)[1].split("</section>", 1)[0]
    strip_links = re.findall(r'href="(/tasks/[^"]*)" class="btn btn-sm shrink-0"', strip)

    assert rows == [("ht-old", "human"), ("rv-1", "review"), ("ht-new", "human")]
    # Human items link to their form; review items to the inbox, where Retry / Fail live
    assert strip_links == ["/tasks/ht-old/", "/tasks/", "/tasks/ht-new/"]
    assert re.search(r">\s*3\s*</span>", badge)

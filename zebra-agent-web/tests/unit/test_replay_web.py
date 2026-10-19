"""Replay from the CLI and the step trace (#170), and the DjangoStore journal fields it needs."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from io import StringIO
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.core.management import call_command
from zebra.core import journal
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessEvent,
    ProcessEventKind,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent_web.api import agent_engine, web_views

CALLS: list[str] = []


class SpendAction(TaskAction):
    """Stands in for an LLM call."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        CALLS.append("spend")
        context.set_process_property("__total_cost__", 0.25)
        context.set_process_property("draft", "a draft")
        return TaskResult.ok(output="a draft")


class BoomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        CALLS.append("boom")
        return TaskResult.fail("the publish step broke")


FLOW = ProcessDefinition(
    id="replay_web_flow",
    name="Draft And Publish",
    first_task_id="draft",
    tasks={
        "draft": TaskDefinition(id="draft", name="Draft", action="spend"),
        "publish": TaskDefinition(id="publish", name="Publish", action="boom"),
    },
    routings=[RoutingDefinition(id="r1", source_task_id="draft", dest_task_id="publish")],
)


@pytest.fixture
def identity(transactional_db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def engine(monkeypatch):
    from zebra_agent_web.storage import DjangoStore

    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("spend", SpendAction)
    registry.register_action("boom", BoomAction)
    wf_engine = WorkflowEngine(DjangoStore(), registry)

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(
        agent_engine,
        "get_agent_loop",
        lambda: SimpleNamespace(engine=wf_engine, goal_timeout=60.0),
    )
    CALLS.clear()
    return wf_engine


async def _failed_run(wf_engine: WorkflowEngine, **props) -> str:
    process = await wf_engine.create_process(FLOW, properties={"goal": "Post it", **props})
    await wf_engine.start_process(process.id)
    return process.id


def _call(*args) -> tuple[dict, int]:
    out = StringIO()
    try:
        call_command("replay_process", *args, stdout=out, stderr=StringIO())
        code = 0
    except SystemExit as e:
        code = e.code
    return json.loads(out.getvalue()), code


# =============================================================================
# DjangoStore
# =============================================================================


@pytest.mark.django_db(transaction=True)
async def test_django_store_keeps_route_and_large_values():
    from zebra_agent_web.storage import DjangoStore

    store = DjangoStore()
    whole = "x" * (journal.MAX_JOURNAL_VALUE_CHARS - 2)
    changed, _ = journal.property_diff({}, {"whole": whole})
    await store.save_process_event(
        ProcessEvent(
            id="e1",
            process_id="p1",
            kind=ProcessEventKind.TASK_COMPLETED,
            changed=changed,
            next_route="approved",
        )
    )

    (loaded,) = await store.load_process_events(["p1"])
    assert loaded.next_route == "approved"
    assert loaded.changed["whole"] == whole


@pytest.mark.django_db(transaction=True)
async def test_django_store_reads_a_blank_route_as_none():
    """Oracle stores "" as NULL and reads NULL back as ""; either way it is no route."""
    from asgiref.sync import sync_to_async
    from zebra_agent_web.api.models import ProcessEventModel
    from zebra_agent_web.storage import DjangoStore

    await sync_to_async(ProcessEventModel.objects.create)(
        id="e2",
        process_id="p2",
        kind=ProcessEventKind.TASK_COMPLETED.value,
        occurred_at=datetime.now(UTC),
        next_route="",
    )

    (loaded,) = await DjangoStore().load_process_events(["p2"])
    assert loaded.next_route is None


# =============================================================================
# manage.py replay_process
# =============================================================================


@pytest.mark.django_db(transaction=True)
def test_cli_replays_a_failed_process_at_no_cost(engine):
    original_id = async_to_sync(_failed_run)(engine, run_id="run-9")
    assert CALLS == ["spend", "boom"]

    result, code = _call(original_id)

    assert code == 0
    assert result["status"] == "failed"
    assert result["replay_of"] == original_id
    assert result["cost"] == 0.0
    assert "the publish step broke" in result["error"]
    assert result["run_id"] is None
    assert CALLS == ["spend", "boom"]  # nothing re-ran


@pytest.mark.django_db(transaction=True)
def test_cli_runs_a_live_step(engine):
    original_id = async_to_sync(_failed_run)(engine)

    result, code = _call(original_id, "--live", "publish")

    assert code == 0
    assert result["live"] == ["publish"]
    assert CALLS == ["spend", "boom", "boom"]  # only the live step ran again


@pytest.mark.django_db(transaction=True)
def test_cli_reports_a_replay_that_cannot_start(engine):
    original_id = async_to_sync(_failed_run)(engine)

    result, code = _call(original_id, "--live", "nope")

    assert code == 1
    assert result["status"] == "error"
    assert "nope" in result["error"]


# =============================================================================
# Step trace Replay form
# =============================================================================


@pytest.mark.django_db(transaction=True)
async def test_replay_form_starts_a_replay_and_opens_its_trace(
    engine, identity, authenticated_async_client
):
    original_id = await _failed_run(engine)

    page = await authenticated_async_client.get(f"/processes/{original_id}/trace/")
    html = page.content.decode()
    assert "Replay this process" in html
    assert 'name="live" value="publish"' in html

    response = await authenticated_async_client.post(f"/processes/{original_id}/replay/")

    assert response.status_code == 302
    replay_id = response["Location"].split("/")[2]
    assert replay_id != original_id
    await asyncio.gather(*web_views._active_tasks.values())
    replayed = await engine.store.load_process(replay_id)
    assert replayed.state == ProcessState.FAILED
    assert CALLS == ["spend", "boom"]

    trace = await authenticated_async_client.get(response["Location"])
    html = trace.content.decode()
    assert "Replay of" in html
    assert f"/processes/{original_id}/trace/" in html


@pytest.mark.django_db(transaction=True)
async def test_replay_form_rejects_a_running_process(engine, identity, authenticated_async_client):
    human = ProcessDefinition(
        id="replay_web_human",
        name="Ask",
        first_task_id="ask",
        tasks={"ask": TaskDefinition(id="ask", name="Ask", auto=False)},
    )
    process = await engine.create_process(human)
    await engine.start_process(process.id)

    response = await authenticated_async_client.post(f"/processes/{process.id}/replay/")

    assert response.status_code == 400
    assert "only finished processes" in response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_replay_form_unknown_process_is_404(engine, identity, authenticated_client):
    assert authenticated_client.post("/processes/nope/replay/").status_code == 404

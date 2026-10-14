"""Step trace across parent and subflows (#184): builder, DjangoStore journal, page."""

from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent_web.api import run_trace


class NoteAction(TaskAction):
    """Writes ``note`` = the task's ``text`` property."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        context.set_process_property("note", task.properties["text"])
        return TaskResult.ok(output=task.properties["text"])


class SpawnAction(TaskAction):
    """Suspends on one CHILD subflow, then completes."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        if context.subflow_results is not None:
            return TaskResult.ok(output="children done")
        child = await context.engine.create_process(
            CHILD,
            properties={"topic": "zebras"},
            parent_process_id=context.process.id,
            parent_task_id=task.id,
        )
        return TaskResult.suspend([child.id])


CHILD = ProcessDefinition(
    id="trace_child",
    name="Research Flow",
    first_task_id="draft",
    tasks={
        "draft": TaskDefinition(
            id="draft", name="Draft answer", action="note", properties={"text": "drafted"}
        ),
        "ask": TaskDefinition(id="ask", name="Ask the user", auto=False),
    },
    routings=[RoutingDefinition(id="r1", source_task_id="draft", dest_task_id="ask")],
)

PARENT = ProcessDefinition(
    id="trace_parent",
    name="Agent Main Loop",
    first_task_id="plan",
    tasks={
        "plan": TaskDefinition(
            id="plan", name="Plan", action="note", properties={"text": "planned"}
        ),
        "spawn": TaskDefinition(id="spawn", name="Execute Workflow", action="spawn"),
    },
    routings=[RoutingDefinition(id="r1", source_task_id="plan", dest_task_id="spawn")],
)


def _engine(store) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_action("note", NoteAction)
    registry.register_action("spawn", SpawnAction)
    return WorkflowEngine(store, registry)


async def _start_run(store, **extra) -> tuple[WorkflowEngine, ProcessInstance]:
    engine = _engine(store)
    properties = {"goal": "Learn", "run_id": "run-1", **extra}
    root = await engine.create_process(PARENT, properties=properties)
    await engine.start_process(root.id)
    return engine, root


# =============================================================================
# Builder
# =============================================================================


async def test_trace_nests_subflow_under_spawning_step_and_shows_where_it_is():
    store = InMemoryStore()
    engine, root = await _start_run(store)

    trace = await run_trace.build_trace(store, root)

    assert trace.is_active
    assert trace.process_count == 2
    plan, spawn = trace.root.steps
    assert (plan.name, plan.state) == ("Plan", "complete")
    assert plan.changed == {"note": "planned", "__task_output_plan": "planned"}
    assert spawn.state == "suspended"
    (child,) = spawn.children
    assert child.name == "Research Flow"
    assert [(s.name, s.state) for s in child.steps] == [
        ("Draft answer", "complete"),
        ("Ask the user", "waiting"),
    ]
    assert trace.current == [
        ["Agent Main Loop", "Execute Workflow", "Research Flow", "Ask the user"]
    ]


async def test_trace_after_completion_has_no_current_step():
    store = InMemoryStore()
    engine, root = await _start_run(store)
    (child_proc,) = await store.list_child_processes(root.id)
    (ask,) = await engine.get_pending_tasks(child_proc.id)
    await engine.complete_task(ask.id, TaskResult.ok(output={"ok": True}))

    root = await store.load_process(root.id)
    trace = await run_trace.build_trace(store, root)

    assert root.state == ProcessState.COMPLETE
    assert not trace.is_active
    assert trace.current == []
    assert [s.state for s in trace.root.steps] == ["complete", "complete"]
    assert trace.root.steps[1].attempts == 1  # resuming after subflows is not a retry


async def test_properties_at_rebuilds_properties_after_each_step():
    store = InMemoryStore()
    _, root = await _start_run(store)
    trace = await run_trace.build_trace(store, root)

    initial = await run_trace.properties_at(store, root.id, trace.root.start_event_id)
    assert initial == {"goal": "Learn", "run_id": "run-1"}
    after_plan = await run_trace.properties_at(store, root.id, trace.root.steps[0].last_event_id)
    assert after_plan == {
        "goal": "Learn",
        "run_id": "run-1",
        "note": "planned",
        "__task_output_plan": "planned",
    }
    assert await run_trace.properties_at(store, root.id, "no-such-event") is None


async def test_find_root_climbs_from_a_subflow():
    store = InMemoryStore()
    _, root = await _start_run(store)
    (child,) = await store.list_child_processes(root.id)

    assert (await run_trace.find_root(store, child.id)).id == root.id
    assert (await run_trace.find_run_root(store, "run-1")).id == root.id


async def test_process_without_journal_still_shows_live_tasks():
    """A run from before the journal: no events, but live tasks are listed."""

    class NoJournalStore(InMemoryStore):
        async def save_process_event(self, event) -> None:
            return None

    store = NoJournalStore()
    _, root = await _start_run(store)
    (child_proc,) = await store.list_child_processes(root.id)

    trace = await run_trace.build_trace(store, root)
    assert not trace.root.has_journal
    (child,) = trace.root.steps[0].children  # the suspended spawn task is still live
    assert child.id == child_proc.id
    assert [s.state for s in child.steps] == ["queued"]  # the READY manual task


def test_split_properties_puts_engine_keys_last():
    workflow, internal = run_trace.split_properties({"b": 1, "__x": 2, "a": 3})
    assert workflow == [("a", 3), ("b", 1)]
    assert internal == [("__x", 2)]


# =============================================================================
# DjangoStore and page
# =============================================================================


@pytest.mark.django_db(transaction=True)
async def test_django_store_journal_round_trip():
    from zebra_agent_web.storage import DjangoStore

    store = DjangoStore()
    _, root = await _start_run(store)

    (child,) = await store.list_child_processes(root.id)
    events = await store.load_process_events([root.id, child.id])
    assert {e.process_id for e in events} == {root.id, child.id}
    assert [e.timestamp for e in events] == sorted(e.timestamp for e in events)
    trace = await run_trace.build_trace(store, root)
    assert trace.current[0][-1] == "Ask the user"

    await store.delete_process(child.id)
    assert await store.load_process_events([child.id]) == []


@pytest.fixture
def identity(transactional_db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def started_run(identity, test_user):
    """A run owned by the signed-in user, parked on the subflow's human task."""
    from zebra_agent_web.storage import DjangoStore

    _, root = async_to_sync(_start_run)(DjangoStore(), __user_id__=test_user.id)
    return root


@pytest.mark.django_db(transaction=True)
def test_trace_page_renders_tree(authenticated_client, started_run):
    response = authenticated_client.get(f"/processes/{started_run.id}/trace/")

    assert response.status_code == 200
    html = response.content.decode()
    for text in ("Step trace", "Agent Main Loop", "Execute Workflow", "Research Flow"):
        assert text in html
    assert "Where it is now" in html
    assert 'hx-trigger="every 5s"' in html  # live refresh while running


@pytest.mark.django_db(transaction=True)
def test_trace_htmx_refresh_returns_only_the_tree(authenticated_client, started_run):
    response = authenticated_client.get(
        f"/processes/{started_run.id}/trace/", headers={"HX-Request": "true"}
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="trace-tree"' in html
    assert "<html" not in html


@pytest.mark.django_db(transaction=True)
def test_trace_properties_partial(authenticated_client, started_run):
    from zebra_agent_web.storage import DjangoStore

    trace = async_to_sync(run_trace.build_trace)(DjangoStore(), started_run)
    event_id = trace.root.steps[0].last_event_id

    response = authenticated_client.get(f"/processes/{started_run.id}/trace/{event_id}/properties/")
    html = response.content.decode()
    assert response.status_code == 200
    assert "planned" in html and "goal" in html
    assert "Engine properties" in html  # __task_output_plan is tucked away

    missing = authenticated_client.get(f"/processes/{started_run.id}/trace/nope/properties/")
    assert missing.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_run_trace_redirects_to_root_process(authenticated_client, started_run):
    response = authenticated_client.get("/runs/run-1/trace/")
    assert response.status_code == 302
    assert response["Location"] == f"/processes/{started_run.id}/trace/"


@pytest.mark.django_db(transaction=True)
def test_trace_unknown_process_is_404(authenticated_client, identity):
    assert authenticated_client.get("/processes/nope/trace/").status_code == 404
    assert authenticated_client.get("/runs/nope/trace/").status_code == 404

"""Process step journal: events per lifecycle step with property diffs (#184)."""

from unittest.mock import patch

import pytest

from zebra.core import engine as engine_module
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
from zebra.storage.memory import InMemoryStore
from zebra.storage.sqlite import SQLiteStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

K = ProcessEventKind


class SetAction(TaskAction):
    """Sets ``key`` to ``value``, drops ``drop`` and outputs ``value``."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        context.set_process_property(task.properties["key"], task.properties["value"])
        context.process.properties.pop(task.properties.get("drop", ""), None)
        return TaskResult.ok(output=task.properties["value"])


class BoomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("boom")


class SpawnAction(TaskAction):
    """Suspends on one CHILD subflow, then completes with its output."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        if context.subflow_results is not None:
            return TaskResult.ok(output=context.subflow_results[0]["output"])
        child = await context.engine.create_process(
            CHILD,
            properties={"n": 1},
            parent_process_id=context.process.id,
            parent_task_id=task.id,
        )
        return TaskResult.suspend([child.id])


def _set(task_id: str, key: str, value, drop: str | None = None) -> TaskDefinition:
    props = {"key": key, "value": value}
    if drop:
        props["drop"] = drop
    return TaskDefinition(id=task_id, name=task_id.title(), action="set", properties=props)


SERIAL = ProcessDefinition(
    id="serial",
    name="Serial",
    first_task_id="one",
    tasks={"one": _set("one", "a", 1), "two": _set("two", "b", 2, drop="tmp")},
    routings=[RoutingDefinition(id="r1", source_task_id="one", dest_task_id="two")],
)

HUMAN = ProcessDefinition(
    id="human",
    name="Human",
    first_task_id="ask",
    tasks={"ask": TaskDefinition(id="ask", name="Ask", auto=False), "two": _set("two", "b", 2)},
    routings=[RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="two")],
)

FAILING = ProcessDefinition(
    id="failing",
    name="Failing",
    first_task_id="work",
    tasks={"work": TaskDefinition(id="work", name="Work", action="boom")},
)

CHILD = ProcessDefinition(
    id="child", name="Child", first_task_id="work", tasks={"work": _set("work", "c", 3)}
)

PARENT = ProcessDefinition(
    id="parent",
    name="Parent",
    first_task_id="spawn",
    tasks={"spawn": TaskDefinition(id="spawn", name="Spawn", action="spawn")},
)


def _registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register_action("set", SetAction)
    registry.register_action("boom", BoomAction)
    registry.register_action("spawn", SpawnAction)
    return registry


@pytest.fixture(params=["memory", "sqlite"])
async def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryStore()
        return
    sqlite = SQLiteStore(tmp_path / "journal.db")
    await sqlite.initialize()
    yield sqlite
    await sqlite.close()


@pytest.fixture
def engine(store):
    return WorkflowEngine(store, _registry())


def _kinds(events: list[ProcessEvent]) -> list[tuple[str, str | None]]:
    return [(e.kind.value, e.task_definition_id) for e in events]


# =============================================================================
# Helpers
# =============================================================================


def test_property_diff_reports_changed_and_removed():
    changed, removed = journal.property_diff({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "d": 4})
    assert changed == {"b": 5, "d": 4}
    assert removed == ["c"]


def test_property_diff_truncates_large_values():
    big = "x" * (journal.MAX_JOURNAL_VALUE_CHARS + 10)
    changed, _ = journal.property_diff({}, {"big": big, "small": "s"})
    assert changed["small"] == "s"
    assert changed["big"][journal.TRUNCATED_KEY] is True
    assert len(changed["big"]["preview"]) == journal.TRUNCATED_PREVIEW_CHARS


def test_replay_applies_events_in_order():
    def ev(changed, removed=()):
        return ProcessEvent(
            id="x", process_id="p", kind=K.TASK_COMPLETED, changed=changed, removed=list(removed)
        )

    states = journal.replay([ev({"a": 1}), ev({"b": 2}), ev({"a": 3}, ["b"])])
    assert states == [{"a": 1}, {"a": 1, "b": 2}, {"a": 3}]


# =============================================================================
# Engine
# =============================================================================


async def test_serial_run_journals_each_step_with_its_changes(engine, store):
    process = await engine.create_process(SERIAL, properties={"goal": "g", "tmp": "t"})
    await engine.start_process(process.id)

    events = await store.load_process_events([process.id])
    assert _kinds(events) == [
        ("process_started", None),
        ("task_started", "one"),
        ("task_completed", "one"),
        ("task_started", "two"),
        ("task_completed", "two"),
        ("process_completed", None),
    ]
    assert events[0].changed == {"goal": "g", "tmp": "t"}
    assert events[2].changed == {"a": 1, "__task_output_one": 1}
    assert events[4].changed == {"b": 2, "__task_output_two": 2}
    assert events[4].removed == ["tmp"]
    assert events[3].changed == {} and events[3].removed == []

    final = await store.load_process(process.id)
    assert final.state == ProcessState.COMPLETE
    assert journal.replay(events)[-1] == final.properties
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps) and len(set(timestamps)) == len(timestamps)


async def test_manual_task_journals_waiting_then_completed(engine, store):
    process = await engine.create_process(HUMAN)
    await engine.start_process(process.id)
    (pending,) = await engine.get_pending_tasks(process.id)

    events = await store.load_process_events([process.id])
    assert _kinds(events)[-1] == ("task_waiting", "ask")

    await engine.complete_task(pending.id, TaskResult.ok(output={"answer": "yes"}))
    events = await store.load_process_events([process.id])
    completed = [e for e in events if e.kind == K.TASK_COMPLETED and e.task_definition_id == "ask"]
    assert completed[0].task_instance_id == pending.id
    assert completed[0].changed == {"__task_output_ask": {"answer": "yes"}}
    assert events[-1].kind == K.PROCESS_COMPLETED


async def test_manual_task_completed_by_a_new_engine_diffs_from_stored_journal(store):
    """After a restart the baseline is rebuilt from stored events, not re-journalled whole."""
    process = await WorkflowEngine(store, _registry()).create_process(HUMAN, properties={"g": 1})
    first = WorkflowEngine(store, _registry())
    await first.start_process(process.id)
    (pending,) = await first.get_pending_tasks(process.id)

    restarted = WorkflowEngine(store, _registry())
    await restarted.complete_task(pending.id, TaskResult.ok(output="ok"))

    events = await store.load_process_events([process.id])
    ask_done = next(e for e in events if e.kind == K.TASK_COMPLETED)
    assert ask_done.changed == {"__task_output_ask": "ok"}
    final = await store.load_process(process.id)
    assert journal.replay(events)[-1] == final.properties


async def test_failed_task_journals_error_on_task_and_process(engine, store):
    process = await engine.create_process(FAILING)
    await engine.start_process(process.id)

    events = await store.load_process_events([process.id])
    assert _kinds(events)[-2:] == [("task_failed", "work"), ("process_failed", None)]
    assert events[-2].error == "boom"
    assert events[-1].error == "boom"


async def test_fail_process_journals_reason(engine, store):
    process = await engine.create_process(HUMAN)
    await engine.start_process(process.id)
    await engine.fail_process(process.id, "Cancelled by user")

    events = await store.load_process_events([process.id])
    assert events[-1].kind == K.PROCESS_FAILED
    assert events[-1].error == "Cancelled by user"
    assert events[-1].changed == {"__error__": "Cancelled by user"}


async def test_subflow_is_linked_to_the_suspended_step(engine, store):
    process = await engine.create_process(PARENT)
    await engine.start_process(process.id)

    (child,) = await store.list_child_processes(process.id)
    assert child.definition_id == "child"
    events = await store.load_process_events([process.id, child.id])
    parent_kinds = _kinds([e for e in events if e.process_id == process.id])
    assert parent_kinds == [
        ("process_started", None),
        ("task_started", "spawn"),
        ("task_suspended", "spawn"),
        ("task_started", "spawn"),
        ("task_completed", "spawn"),
        ("process_completed", None),
    ]
    spawn_ids = {e.task_instance_id for e in events if e.task_definition_id == "spawn"}
    assert spawn_ids == {child.parent_task_id}
    child_kinds = _kinds([e for e in events if e.process_id == child.id])
    assert child_kinds[-1] == ("process_completed", None)


async def test_journal_failure_never_fails_the_workflow():
    class BrokenJournalStore(InMemoryStore):
        async def save_process_event(self, event: ProcessEvent) -> None:
            raise RuntimeError("journal down")

    store = BrokenJournalStore()
    engine = WorkflowEngine(store, _registry())
    process = await engine.create_process(SERIAL)
    with patch.object(engine_module.logger, "warning") as warning:
        await engine.start_process(process.id)

    final = await store.load_process(process.id)
    assert final.state == ProcessState.COMPLETE
    assert any("Could not journal" in c.args[0] for c in warning.call_args_list)


async def test_nested_value_mutated_in_place_is_journalled(store):
    """An action editing a nested property in place still shows in the diff."""

    class AppendAction(TaskAction):
        async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
            context.process.properties["log"]["items"].append("second")
            return TaskResult.ok()

    registry = _registry()
    registry.register_action("append", AppendAction)
    definition = ProcessDefinition(
        id="append",
        name="Append",
        first_task_id="add",
        tasks={"add": TaskDefinition(id="add", name="Add", action="append")},
    )
    engine = WorkflowEngine(store, registry)
    process = await engine.create_process(definition, properties={"log": {"items": ["first"]}})
    await engine.start_process(process.id)

    events = await store.load_process_events([process.id])
    completed = next(e for e in events if e.kind == K.TASK_COMPLETED)
    assert completed.changed == {"log": {"items": ["first", "second"]}}
    assert journal.replay(events)[0] == {"log": {"items": ["first"]}}


async def test_delete_process_removes_its_events(engine, store):
    process = await engine.create_process(SERIAL)
    await engine.start_process(process.id)
    await store.delete_process(process.id)
    assert await store.load_process_events([process.id]) == []


async def test_parent_link_set_after_create_is_persisted(engine, store):
    """Spawners set the parent link on an already-saved process; the store must keep it."""
    parent = await engine.create_process(SERIAL)
    child = await engine.create_process(CHILD)
    child.parent_process_id = parent.id
    child.parent_task_id = "task-1"
    await store.save_process(child)

    (loaded,) = await store.list_child_processes(parent.id)
    assert loaded.id == child.id
    assert loaded.parent_task_id == "task-1"


# =============================================================================
# Recording for replay (#170)
# =============================================================================


async def test_event_route_and_large_values_round_trip(store):
    cap = journal.MAX_JOURNAL_VALUE_CHARS  # JSON adds two quotes to a string
    under = "u" * (cap - 3)  # one under the cap
    at_cap = "x" * (cap - 2)  # exactly at it
    over = "y" * (cap - 1)  # one over
    changed, _ = journal.property_diff({}, {"under": under, "at_cap": at_cap, "over": over})
    await store.save_process_event(
        ProcessEvent(
            id="e1",
            process_id="p",
            kind=K.TASK_COMPLETED,
            task_instance_id="t",
            task_definition_id="decide",
            changed=changed,
            next_route="approved",
        )
    )

    (loaded,) = await store.load_process_events(["p"])
    assert loaded.next_route == "approved"
    assert loaded.changed["under"] == under
    assert loaded.changed["at_cap"] == at_cap
    assert loaded.changed["over"][journal.TRUNCATED_KEY] is True
    assert loaded.changed["over"]["size"] == cap + 1


async def test_sqlite_journal_from_before_routes_gains_the_column(tmp_path):
    import aiosqlite

    path = tmp_path / "old.db"
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            "CREATE TABLE process_events (id TEXT PRIMARY KEY, process_id TEXT NOT NULL, "
            "kind TEXT NOT NULL, task_instance_id TEXT, task_definition_id TEXT, "
            "attempt INTEGER NOT NULL DEFAULT 0, timestamp TEXT NOT NULL, "
            "changed JSON NOT NULL DEFAULT '{}', removed JSON NOT NULL DEFAULT '[]', error TEXT)"
        )
        await conn.commit()

    sqlite = SQLiteStore(path)
    await sqlite.initialize()
    try:
        await sqlite.save_process_event(
            ProcessEvent(id="e", process_id="p", kind=K.TASK_COMPLETED, next_route="r")
        )
        (loaded,) = await sqlite.load_process_events(["p"])
        assert loaded.next_route == "r"
    finally:
        await sqlite.close()

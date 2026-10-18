"""Replay a finished process from its step journal (#170)."""

import pytest

from zebra.core import journal, replay
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

#: Action name -> number of times it ran, reset per test.
CALLS: dict[str, int] = {}


def _count(name: str) -> None:
    CALLS[name] = CALLS.get(name, 0) + 1


class SpendAction(TaskAction):
    """Stands in for an LLM call: spends, sets ``key`` and outputs a fresh value."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("spend")
        total = context.get_process_property("__total_cost__", 0.0)
        context.set_process_property("__total_cost__", total + 0.5)
        value = f"{task.properties['key']}-{CALLS['spend']}"
        context.set_process_property(task.properties["key"], value)
        return TaskResult.ok(output=value)


class DecideAction(TaskAction):
    """Routes on the ``choice`` property."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("decide")
        return TaskResult(
            success=True, output="decided", next_route=context.process.properties["choice"]
        )


class BoomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("boom")
        return TaskResult.fail("boom")


class FixedAction(TaskAction):
    """The fixed version of ``boom``, registered under the same name."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("fixed")
        return TaskResult.ok(output="fixed")


class CopyAction(TaskAction):
    """Copies the ``work`` step's output into ``seen``."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("copy")
        context.set_process_property("seen", context.process.properties.get("__task_output_work"))
        return TaskResult.ok(output="copied")


class LoopAction(TaskAction):
    """Increments ``i``; routes ``again`` until it reaches 3."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("loop")
        i = context.get_process_property("i", 0) + 1
        context.set_process_property("i", i)
        return TaskResult(success=True, output=i, next_route="again" if i < 3 else "done")


class SpawnAction(TaskAction):
    """Suspends on one CHILD subflow, then completes with its output."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _count("spawn")
        if context.subflow_results is not None:
            return TaskResult.ok(output=context.subflow_results[0]["output"])
        child = await context.engine.create_process(
            CHILD, parent_process_id=context.process.id, parent_task_id=task.id
        )
        return TaskResult.suspend([child.id])


def _spend(task_id: str, key: str) -> TaskDefinition:
    return TaskDefinition(id=task_id, name=task_id.title(), action="spend", properties={"key": key})


def _route(source: str, dest: str | None, name: str | None = None) -> RoutingDefinition:
    return RoutingDefinition(
        id=f"{source}-{dest}-{name}",
        source_task_id=source,
        dest_task_id=dest,
        name=name,
        condition="route_name" if name else None,
    )


# decide --approved--> plan (spend) -> work (boom); --rejected--> stop
FAILING = ProcessDefinition(
    id="failing",
    name="Failing",
    first_task_id="decide",
    tasks={
        "decide": TaskDefinition(id="decide", name="Decide", action="decide"),
        "plan": _spend("plan", "plan_text"),
        "stop": _spend("stop", "stopped"),
        "work": TaskDefinition(id="work", name="Work", action="boom"),
        "after": TaskDefinition(id="after", name="After", action="copy"),
    },
    routings=[
        _route("decide", "plan", "approved"),
        _route("decide", "stop", "rejected"),
        _route("plan", "work"),
        _route("work", "after"),
    ],
)

# ask (human, routes yes/no) -> yes: spend
HUMAN = ProcessDefinition(
    id="human",
    name="Human",
    first_task_id="ask",
    tasks={
        "ask": TaskDefinition(id="ask", name="Ask", auto=False),
        "yes": _spend("yes", "said_yes"),
        "no": _spend("no", "said_no"),
    },
    routings=[_route("ask", "yes", "yes"), _route("ask", "no", "no")],
)

LOOP = ProcessDefinition(
    id="loop",
    name="Loop",
    first_task_id="step",
    tasks={
        "step": TaskDefinition(id="step", name="Step", action="loop"),
        "end": _spend("end", "ended"),
    },
    routings=[_route("step", "step", "again"), _route("step", "end", "done")],
)

CHILD = ProcessDefinition(
    id="child", name="Child", first_task_id="work", tasks={"work": _spend("work", "c")}
)

PARENT = ProcessDefinition(
    id="parent",
    name="Parent",
    first_task_id="spawn",
    tasks={
        "spawn": TaskDefinition(id="spawn", name="Spawn", action="spawn"),
        "after": _spend("after", "a"),
    },
    routings=[_route("spawn", "after")],
)


def _registry(**overrides: type[TaskAction]) -> ActionRegistry:
    registry = ActionRegistry()
    registry.register_defaults()
    actions = {
        "spend": SpendAction,
        "decide": DecideAction,
        "boom": BoomAction,
        "copy": CopyAction,
        "loop": LoopAction,
        "spawn": SpawnAction,
        **overrides,
    }
    for name, action in actions.items():
        registry.register_action(name, action)
    return registry


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()


@pytest.fixture(params=["memory", "sqlite"])
async def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryStore()
        return
    sqlite = SQLiteStore(tmp_path / "replay.db")
    await sqlite.initialize()
    yield sqlite
    await sqlite.close()


@pytest.fixture
def engine(store):
    return WorkflowEngine(store, _registry())


async def _run(engine, definition, **properties):
    process = await engine.create_process(definition, properties=properties)
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def _replay(engine, process_id, **kwargs):
    replayed = await engine.create_replay(process_id, **kwargs)
    await engine.start_process(replayed.id)
    return await engine.store.load_process(replayed.id)


def _workflow_props(properties: dict) -> dict:
    """Properties a replay must reproduce: all but spend, run id and the marker."""
    skip = replay.UNREPLAYED_KEYS | {"run_id", replay.REPLAY_KEY}
    return {k: v for k, v in properties.items() if k not in skip}


# =============================================================================
# Unchanged replay (O1, O2)
# =============================================================================


async def test_unchanged_replay_reproduces_a_failure_without_running_anything(engine, store):
    original = await _run(engine, FAILING, goal="g", choice="approved", run_id="run-1")
    assert original.state == ProcessState.FAILED
    assert original.properties["__total_cost__"] == 0.5
    calls_before = dict(CALLS)
    events_before = await store.load_process_events([original.id])

    replayed = await _replay(engine, original.id)

    assert CALLS == calls_before  # no action ran
    assert replayed.state == ProcessState.FAILED
    assert replayed.properties["__error__"] == original.properties["__error__"]
    assert _workflow_props(replayed.properties) == _workflow_props(original.properties)
    assert "__total_cost__" not in replayed.properties
    assert "run_id" not in replayed.properties
    assert replayed.properties[replay.REPLAY_KEY]["of"] == original.id
    # The original is untouched.
    assert await store.load_process(original.id) == original
    assert await store.load_process_events([original.id]) == events_before


async def test_replay_follows_the_route_the_original_took(engine):
    original = await _run(engine, FAILING, choice="rejected")
    assert original.state == ProcessState.COMPLETE
    calls_before = dict(CALLS)

    # The replay starts with the original's properties, so even with a
    # different choice now, the recorded route is what it follows.
    replayed = await _replay(engine, original.id)

    assert CALLS == calls_before
    assert replayed.state == ProcessState.COMPLETE
    assert replayed.properties["stopped"] == original.properties["stopped"]
    assert "plan_text" not in replayed.properties


async def test_human_step_is_served_without_waiting(engine):
    process = await engine.create_process(HUMAN)
    await engine.start_process(process.id)
    (ask,) = await engine.get_pending_tasks(process.id)
    await engine.complete_task(ask.id, TaskResult(success=True, output={"a": 1}, next_route="no"))
    original = await engine.store.load_process(process.id)
    calls_before = dict(CALLS)

    replayed = await _replay(engine, original.id)

    assert CALLS == calls_before
    assert replayed.state == ProcessState.COMPLETE
    assert await engine.get_pending_tasks(replayed.id) == []
    assert replayed.properties["__task_output_ask"] == {"a": 1}
    assert replayed.properties["said_no"] == original.properties["said_no"]
    assert "said_yes" not in replayed.properties


async def test_loop_replays_each_iteration_in_order(engine):
    original = await _run(engine, LOOP)
    assert original.properties["i"] == 3
    calls_before = dict(CALLS)

    replayed = await _replay(engine, original.id)

    assert CALLS == calls_before
    assert replayed.state == ProcessState.COMPLETE
    assert _workflow_props(replayed.properties) == _workflow_props(original.properties)
    assert replayed.properties[replay.REPLAY_KEY]["served"] == {"step": 3, "end": 1}


async def test_subflow_step_is_served_without_starting_children(engine, store):
    original = await _run(engine, PARENT)
    assert original.state == ProcessState.COMPLETE
    calls_before = dict(CALLS)

    replayed = await _replay(engine, original.id)

    assert CALLS == calls_before
    assert replayed.state == ProcessState.COMPLETE
    assert _workflow_props(replayed.properties) == _workflow_props(original.properties)
    assert len(await store.list_child_processes(original.id)) == 1
    assert await store.list_child_processes(replayed.id) == []


async def test_replay_of_a_replay_reproduces_the_same_outcome(engine):
    original = await _run(engine, FAILING, choice="approved")
    first = await _replay(engine, original.id)
    second = await _replay(engine, first.id)
    assert second.state == ProcessState.FAILED
    assert _workflow_props(second.properties) == _workflow_props(original.properties)


async def test_restarted_engine_continues_a_replay_from_the_journal(store):
    original = await _run(WorkflowEngine(store, _registry()), LOOP)
    replayed = await _replay(WorkflowEngine(store, _registry()), original.id)
    assert replayed.state == ProcessState.COMPLETE
    assert CALLS == {"loop": 3, "spend": 1}


# =============================================================================
# Live steps (O3)
# =============================================================================


async def test_live_step_runs_while_the_rest_replays(store):
    original = await _run(WorkflowEngine(store, _registry()), FAILING, choice="approved")
    CALLS.clear()
    fixed = WorkflowEngine(store, _registry(boom=FixedAction))

    replayed = await _replay(fixed, original.id, live=["work"], continue_live=True)

    assert CALLS == {"fixed": 1, "copy": 1}  # plan (spend) was served
    assert replayed.state == ProcessState.COMPLETE
    assert replayed.properties["plan_text"] == original.properties["plan_text"]
    assert replayed.properties["seen"] == "fixed"


async def test_changed_step_in_a_replacement_definition_runs_live(store):
    original = await _run(WorkflowEngine(store, _registry()), FAILING, choice="approved")
    CALLS.clear()
    tasks = dict(FAILING.tasks)
    tasks["work"] = TaskDefinition(id="work", name="Work", action="fixed")
    changed = FAILING.model_copy(update={"tasks": tasks})
    engine = WorkflowEngine(store, _registry(fixed=FixedAction))

    replayed = await _replay(engine, original.id, definition=changed, continue_live=True)

    assert replayed.properties[replay.REPLAY_KEY]["live"] == ["work"]
    assert CALLS == {"fixed": 1, "copy": 1}
    assert replayed.state == ProcessState.COMPLETE
    assert replayed.definition_id.startswith("failing-replay-")
    assert (await store.load_definition("failing")).tasks["work"].action == "boom"


async def test_live_human_step_waits_for_a_person(engine):
    process = await engine.create_process(HUMAN)
    await engine.start_process(process.id)
    (ask,) = await engine.get_pending_tasks(process.id)
    await engine.complete_task(ask.id, TaskResult(success=True, next_route="yes"))

    replayed = await engine.create_replay(process.id, live=["ask"])
    await engine.start_process(replayed.id)

    (pending,) = await engine.get_pending_tasks(replayed.id)
    assert pending.task_definition_id == "ask"


# =============================================================================
# Leaving the recording (O4)
# =============================================================================


async def test_step_past_the_recording_fails_naming_it(store):
    original = await _run(WorkflowEngine(store, _registry()), FAILING, choice="approved")
    fixed = WorkflowEngine(store, _registry(boom=FixedAction))

    replayed = await _replay(fixed, original.id, live=["work"])

    assert replayed.state == ProcessState.FAILED
    error = replayed.properties["__error__"]
    assert "Replay cannot serve step 'after' (run #1)" in error
    assert "the original never ran it" in error
    assert "Run it live" in error
    assert "copy" not in CALLS


async def test_truncated_recording_fails_naming_the_value(engine, store):
    original = await _run(engine, LOOP)
    events = await store.load_process_events([original.id])
    end = next(e for e in events if e.kind == ProcessEventKind.TASK_COMPLETED)
    tampered = end.model_copy(
        update={"changed": {**end.changed, "i": {journal.TRUNCATED_KEY: True, "size": 9}}}
    )
    store_events = [tampered if e.id == end.id else e for e in events]
    steps = replay.recorded_steps(store_events, LOOP)
    assert steps["step"][0].truncated_keys() == ["i"]

    engine._recordings[original.id] = steps
    replayed = await _replay(engine, original.id)

    assert replayed.state == ProcessState.FAILED
    assert "Replay cannot serve step 'step' (run #1)" in replayed.properties["__error__"]
    assert "its recorded i was too large to keep" in replayed.properties["__error__"]


async def test_old_events_without_a_route_follow_the_path_taken(engine, store):
    original = await _run(engine, FAILING, choice="rejected")
    events = await store.load_process_events([original.id])
    legacy = [e.model_copy(update={"next_route": None}) for e in events]

    steps = replay.recorded_steps(legacy, FAILING)

    assert steps["decide"][0].next_route == "rejected"


async def test_route_is_journalled_on_task_end(engine, store):
    original = await _run(engine, FAILING, choice="rejected")
    events = await store.load_process_events([original.id])
    decide_end = next(
        e
        for e in events
        if e.kind == ProcessEventKind.TASK_COMPLETED and e.task_definition_id == "decide"
    )
    assert decide_end.next_route == "rejected"


async def test_running_process_cannot_be_replayed(engine):
    process = await engine.create_process(HUMAN)
    await engine.start_process(process.id)
    with pytest.raises(replay.ReplayError, match="only finished processes"):
        await engine.create_replay(process.id)


async def test_process_without_history_cannot_be_replayed(engine, store):
    process = await engine.create_process(LOOP)
    await store.save_process(process.model_copy(update={"state": ProcessState.COMPLETE}))
    with pytest.raises(replay.ReplayError, match="no step history"):
        await engine.create_replay(process.id)


async def test_unknown_live_step_is_rejected(engine):
    original = await _run(engine, LOOP)
    with pytest.raises(replay.ReplayError, match="nope"):
        await engine.create_replay(original.id, live=["nope"])


# =============================================================================
# Recording helpers
# =============================================================================


def test_recorded_step_folds_events_after_the_first():
    def ev(kind, changed=None, removed=(), task="t1", route=None):
        return ProcessEvent(
            id=f"{kind}-{len(changed or {})}",
            process_id="p",
            kind=kind,
            task_instance_id=task,
            task_definition_id="work",
            changed=changed or {},
            removed=list(removed),
            next_route=route,
        )

    K = ProcessEventKind
    events = [
        ProcessEvent(id="s", process_id="p", kind=K.PROCESS_STARTED, changed={"goal": "g"}),
        ev(K.TASK_STARTED, {"before": 1}),
        ev(K.TASK_SUSPENDED, {"x": 1, "__total_cost__": 0.2}),
        ev(K.TASK_STARTED, {"y": 2}, removed=["goal"]),
        ev(K.TASK_COMPLETED, {"__task_output_work": "out"}, route="next"),
    ]
    definition = ProcessDefinition(
        id="d", name="D", first_task_id="work", tasks={"work": TaskDefinition(id="work", name="W")}
    )

    (step,) = replay.recorded_steps(events, definition)["work"]

    assert step.changed == {"x": 1, "__total_cost__": 0.2, "y": 2, "__task_output_work": "out"}
    assert step.removed == ["goal"]
    assert step.output == "out" and step.next_route == "next" and step.success
    props = {"goal": "g", "before": 1}
    step.apply(props)
    assert props == {"before": 1, "x": 1, "y": 2, "__task_output_work": "out"}


def test_interrupted_instance_is_not_recorded():
    events = [
        ProcessEvent(id="s", process_id="p", kind=ProcessEventKind.PROCESS_STARTED),
        ProcessEvent(
            id="t",
            process_id="p",
            kind=ProcessEventKind.TASK_STARTED,
            task_instance_id="t1",
            task_definition_id="work",
        ),
    ]
    assert replay.recorded_steps(events, CHILD) == {}

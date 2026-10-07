"""Tests for find_pending_human_task and GoalTracker (#141)."""

import asyncio

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_agent.human_tasks import find_pending_human_task
from zebra_agent.scheduler.goal_tracker import DAEMON_STARTED_KEY, GoalTracker

AUTO_ONLY = """
name: "Auto Only"
first_task: work
tasks:
  work:
    name: "Work"
"""

MAIN_HUMAN = """
name: "Main Human"
first_task: ask
tasks:
  ask:
    name: "Ask Human"
    auto: false
  after:
    name: "After"
routings:
  - from: ask
    to: after
"""

CHILD_HUMAN = """
name: "Child Human"
first_task: ask
tasks:
  ask:
    name: "Child Form"
    auto: false
"""

PARENT_OF_CHILD = """
name: "Parent"
first_task: spawn
tasks:
  spawn:
    name: "Spawn Child"
    action: spawn_child_and_wait
"""

BLOCKING = """
name: "Blocking"
first_task: block
tasks:
  block:
    name: "Block"
    action: block_forever
"""


class SpawnChildAndWait(TaskAction):
    """Mimics execute_goal_workflow: start a child and poll until it terminates."""

    async def run(self, task, context):
        child_def = load_definition_from_yaml(CHILD_HUMAN)
        child = await context.engine.create_process(child_def)
        child.parent_process_id = context.process.id
        child.parent_task_id = task.id
        await context.store.save_process(child)
        await context.engine.start_process(child.id)
        while True:
            child = await context.store.load_process(child.id)
            if child.state in (ProcessState.COMPLETE, ProcessState.FAILED):
                return TaskResult.ok(output={"child": child.state.value})
            await asyncio.sleep(0.01)


class BlockForever(TaskAction):
    async def run(self, task, context):
        await asyncio.Event().wait()
        return TaskResult.ok()


@pytest.fixture
def engine():
    registry = ActionRegistry()
    registry.register_action("spawn_child_and_wait", SpawnChildAndWait)
    registry.register_action("block_forever", BlockForever)
    return WorkflowEngine(InMemoryStore(), registry)


async def _queue(engine, yaml, **props):
    return await engine.create_process(
        load_definition_from_yaml(yaml), properties={"run_id": "r1", **props}
    )


async def _child_of(engine, parent_id):
    running = await engine.store.get_processes_by_state(ProcessState.RUNNING)
    return next(p for p in running if p.parent_process_id == parent_id)


class TestFindPendingHumanTask:
    async def test_none_for_auto_only(self, engine):
        process = await _queue(engine, AUTO_ONLY)
        await engine.start_process(process.id)
        assert await find_pending_human_task(engine, process.id) is None

    async def test_finds_task_in_main_process(self, engine):
        process = await _queue(engine, MAIN_HUMAN)
        await engine.start_process(process.id)
        task, name = await find_pending_human_task(engine, process.id)
        assert name == "Ask Human"
        assert task.task_definition_id == "ask"

    async def test_finds_task_in_child_process(self, engine):
        process = await _queue(engine, PARENT_OF_CHILD)
        runner = asyncio.create_task(engine.start_process(process.id))
        try:
            for _ in range(200):
                found = await find_pending_human_task(engine, process.id)
                if found:
                    break
                await asyncio.sleep(0.01)
            assert found is not None
            assert found[1] == "Child Form"
        finally:
            runner.cancel()


class TestGoalTracker:
    async def test_auto_only_goal_finishes_and_reconciles_once(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, AUTO_ONLY)

        goal = await tracker.start(process)
        outcome, _ = await tracker.wait(goal, poll_interval=0.01)

        assert outcome == "finished"
        finished = await tracker.reconcile()
        assert [p.id for p in finished] == [process.id]
        assert finished[0].state == ProcessState.COMPLETE
        assert finished[0].properties[DAEMON_STARTED_KEY] is True
        assert await tracker.reconcile() == []

    async def test_main_process_human_task_hands_off(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, MAIN_HUMAN)

        goal = await tracker.start(process)
        outcome, task_name = await tracker.wait(goal, poll_interval=0.01)

        assert (outcome, task_name) == ("awaiting_human", "Ask Human")
        assert await tracker.active_goals() == []
        assert await tracker.reconcile() == []  # still tracked, not finished
        assert [g.process_id for g in tracker.goals] == [process.id]

        # The human answers (via the web, which drives the rest inline)
        pending = await engine.get_pending_tasks(process.id)
        await engine.complete_task(pending[0].id, TaskResult.ok(output={}))

        finished = await tracker.reconcile()
        assert [p.id for p in finished] == [process.id]
        assert tracker.goals == []

    async def test_child_human_task_hands_off_while_still_executing(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, PARENT_OF_CHILD)

        goal = await tracker.start(process)
        outcome, task_name = await tracker.wait(goal, poll_interval=0.01)

        assert (outcome, task_name) == ("awaiting_human", "Child Form")
        assert goal.executing  # start_process is still blocked on the child
        assert await tracker.active_goals() == []  # ...but waiting on a human

        child = await _child_of(engine, process.id)
        pending = await engine.get_pending_tasks(child.id)
        await engine.complete_task(pending[0].id, TaskResult.ok(output={}))
        await asyncio.wait_for(goal.task, timeout=5)

        finished = await tracker.reconcile()
        assert [p.id for p in finished] == [process.id]
        assert finished[0].state == ProcessState.COMPLETE

    async def test_executing_goal_is_active(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, BLOCKING)
        goal = await tracker.start(process)
        await asyncio.sleep(0.05)

        assert [g.process_id for g in await tracker.active_goals()] == [process.id]
        goal.task.cancel()

    async def test_halt_and_cancel_active_fails_process(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, BLOCKING)
        goal = await tracker.start(process)

        async def halted():
            return True

        outcome, _ = await tracker.wait(goal, poll_interval=0.01, should_stop=halted)
        assert outcome == "halted"

        cancelled = await tracker.cancel_active("Kill switch activated")

        assert cancelled == [process.id]
        assert goal.task is None
        stored = await engine.store.load_process(process.id)
        assert stored.state == ProcessState.FAILED
        assert stored.properties["__error__"] == "Kill switch activated"
        assert tracker.goals == []

    async def test_cancel_active_leaves_goals_awaiting_human(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, PARENT_OF_CHILD)
        goal = await tracker.start(process)
        await tracker.wait(goal, poll_interval=0.01)

        assert await tracker.cancel_active("Kill switch activated") == []
        assert (await engine.store.load_process(process.id)).state == ProcessState.RUNNING
        goal.task.cancel()

    async def test_seed_resumes_marked_running_goals_only(self, engine):
        marked = await _queue(engine, MAIN_HUMAN, **{DAEMON_STARTED_KEY: True})
        unmarked = await _queue(engine, MAIN_HUMAN)
        await engine.start_process(marked.id)
        await engine.start_process(unmarked.id)

        tracker = GoalTracker(engine)
        await tracker.seed()
        await tracker.seed()  # idempotent

        assert [g.process_id for g in tracker.goals] == [marked.id]
        assert tracker.goals[0].task is None
        assert await tracker.active_goals() == []  # no live task → never blocks

        pending = await engine.get_pending_tasks(marked.id)
        await engine.complete_task(pending[0].id, TaskResult.ok(output={}))
        assert [p.id for p in await tracker.reconcile()] == [marked.id]
        assert await tracker.reconcile() == []  # recorded exactly once

    async def test_crashed_start_not_left_created_is_dropped(self, engine):
        tracker = GoalTracker(engine)
        process = await _queue(engine, AUTO_ONLY)

        async def boom(process_id):
            raise RuntimeError("start failed")

        engine.start_process = boom
        goal = await tracker.start(process)
        outcome, _ = await tracker.wait(goal, poll_interval=0.01)

        assert outcome == "stalled"
        assert await tracker.reconcile() == []
        assert tracker.goals == []  # still CREATED → the queue will pick it up again

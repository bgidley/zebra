"""Daemon _tick hands off goals waiting on a human and reconciles them later (#141)."""

import asyncio
import contextlib
import io
import logging
from unittest.mock import AsyncMock, patch

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.scheduler import GoalScheduler
from zebra_agent.scheduler.goal_tracker import GoalTracker
from zebra_agent_web.api.daemon import _tick
from zebra_agent_web.api.metrics import goals_completed

HUMAN = """
name: "Needs Human"
first_task: ask
tasks:
  ask:
    name: "Resolve Ethics Dilemma"
    auto: false
"""

AUTO = """
name: "Auto"
first_task: work
tasks:
  work:
    name: "Work"
"""

BLOCKING = """
name: "Blocking"
first_task: block
tasks:
  block:
    name: "Block"
    action: block_forever
"""


class BlockForever(TaskAction):
    async def run(self, task, context):
        await asyncio.Event().wait()
        return TaskResult.ok()


@pytest.fixture
def engine():
    registry = ActionRegistry()
    registry.register_action("block_forever", BlockForever)
    return WorkflowEngine(InMemoryStore(), registry)


@pytest.fixture
def budget_manager():
    manager = AsyncMock()
    manager.get_status = AsyncMock(
        return_value={"available": 10.0, "spent_today": 0.0, "paced_allowance": 50.0}
    )
    return manager


@contextlib.contextmanager
def _daemon_log():
    """Capture daemon log lines (the project logging config doesn't propagate to caplog)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    log = logging.getLogger("zebra_agent_web.api.daemon")
    old_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        yield buf
    finally:
        log.removeHandler(handler)
        log.setLevel(old_level)


def _halted(value: bool):
    return patch("zebra_agent_web.api.kill_switch.is_halted", new=AsyncMock(return_value=value))


async def _queue(engine, yaml, run_id):
    return await engine.create_process(
        load_definition_from_yaml(yaml), properties={"run_id": run_id, "goal": run_id}
    )


async def _tick_once(engine, budget_manager, tracker, scheduler=None):
    await _tick(
        scheduler=scheduler or GoalScheduler(engine.store),
        budget_manager=budget_manager,
        engine=engine,
        dry_run=False,
        tracker=tracker,
        poll_interval=0.01,
    )


async def test_human_task_does_not_block_next_goal(engine, budget_manager):
    tracker = GoalTracker(engine)
    waiting = await _queue(engine, HUMAN, "waiting")
    nxt = await _queue(engine, AUTO, "next")
    success_before = goals_completed.labels(status="success")._value.get()

    with _halted(False), _daemon_log() as log:
        await _tick_once(engine, budget_manager, tracker)
        assert "[daemon:await]" in log.getvalue()
        assert (await engine.store.load_process(waiting.id)).state == ProcessState.RUNNING

        # Next tick is free to run the next queued goal to completion
        await _tick_once(engine, budget_manager, tracker)
        assert (await engine.store.load_process(nxt.id)).state == ProcessState.COMPLETE

        # The human answers; the following tick records the parked goal's outcome once
        pending = await engine.get_pending_tasks(waiting.id)
        await engine.complete_task(pending[0].id, TaskResult.ok(output={}))
        await _tick_once(engine, budget_manager, tracker)
        await _tick_once(engine, budget_manager, tracker)

    assert log.getvalue().count(f"[daemon:done] {waiting.id[:12]}") == 1
    assert goals_completed.labels(status="success")._value.get() == success_before + 2
    assert tracker.goals == []


async def test_executing_goal_blocks_pickup(engine, budget_manager):
    tracker = GoalTracker(engine)
    blocking = await _queue(engine, BLOCKING, "blocking")
    goal = await tracker.start(blocking)
    await asyncio.sleep(0.02)
    scheduler = AsyncMock()

    with _halted(False):
        await _tick_once(engine, budget_manager, tracker, scheduler=scheduler)

    scheduler.pick_next.assert_not_called()
    goal.task.cancel()


async def test_kill_switch_cancels_executing_goal(engine, budget_manager):
    tracker = GoalTracker(engine)
    blocking = await _queue(engine, BLOCKING, "blocking")
    await tracker.start(blocking)
    await asyncio.sleep(0.02)
    scheduler = AsyncMock()

    with _halted(True):
        await _tick_once(engine, budget_manager, tracker, scheduler=scheduler)

    scheduler.pick_next.assert_not_called()
    stored = await engine.store.load_process(blocking.id)
    assert stored.state == ProcessState.FAILED
    assert stored.properties["__error__"] == "Kill switch activated"


async def test_kill_switch_mid_flight_cancels_picked_goal(engine, budget_manager):
    blocking = await _queue(engine, BLOCKING, "blocking")
    halted = AsyncMock(side_effect=[False, True])  # clear at pickup, set mid-flight

    with patch("zebra_agent_web.api.kill_switch.is_halted", new=halted):
        await _tick_once(engine, budget_manager, GoalTracker(engine))

    stored = await engine.store.load_process(blocking.id)
    assert stored.state == ProcessState.FAILED
    assert stored.properties["__error__"] == "Kill switch activated"

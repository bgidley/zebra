"""Daemon _tick() bounds a goal's inline run (GitLab #142).

start_process() runs auto tasks inline, so before #142 a slow goal blocked the
daemon indefinitely and the kill switch could not interrupt it. Uses a real
engine + InMemoryStore with a slow action.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry


class _SlowAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(30)
        return TaskResult.ok(output="too late")


async def _queued_slow_goal() -> tuple[WorkflowEngine, str]:
    registry = ActionRegistry()
    registry.register_action("slow", _SlowAction)
    engine = WorkflowEngine(InMemoryStore(), registry)
    definition = ProcessDefinition(
        id="slow-goal",
        name="Slow Goal",
        first_task_id="work",
        tasks={"work": TaskDefinition(id="work", name="Work", action="slow")},
        routings=[],
    )
    process = await engine.create_process(definition, properties={"goal": "go", "run_id": "r1"})
    return engine, process.id


def _mocks(engine: WorkflowEngine, process_id: str):
    async def _pick_next():
        return await engine.store.load_process(process_id)

    scheduler = AsyncMock()
    scheduler.pick_next = AsyncMock(side_effect=_pick_next)
    budget_manager = AsyncMock()
    budget_manager.get_status = AsyncMock(
        return_value={"available": 10.0, "spent_today": 0.0, "paced_allowance": 50.0}
    )
    return scheduler, budget_manager


def test_slow_goal_is_failed_at_goal_timeout():
    from zebra_agent_web.api.daemon import _tick

    async def _run():
        engine, pid = await _queued_slow_goal()
        scheduler, budget_manager = _mocks(engine, pid)
        loop = asyncio.get_running_loop()
        began = loop.time()
        with patch("zebra_agent_web.api.kill_switch.is_halted", new=AsyncMock(return_value=False)):
            await _tick(
                scheduler=scheduler,
                budget_manager=budget_manager,
                engine=engine,
                dry_run=False,
                goal_timeout=0.2,
            )
        return loop.time() - began, await engine.store.load_process(pid)

    elapsed, process = asyncio.run(_run())

    assert elapsed < 5
    assert process.state == ProcessState.FAILED
    assert "Timed out after 0.2s" in process.properties["__error__"]


def test_kill_switch_cancels_running_goal():
    from zebra_agent_web.api.daemon import KILL_SWITCH_REASON, _tick

    async def _run():
        engine, pid = await _queued_slow_goal()
        scheduler, budget_manager = _mocks(engine, pid)
        # Not halted at pickup, halted on the first mid-run check.
        halted = AsyncMock(side_effect=[False, True, True, True])
        loop = asyncio.get_running_loop()
        began = loop.time()
        with patch("zebra_agent_web.api.kill_switch.is_halted", new=halted):
            await _tick(
                scheduler=scheduler,
                budget_manager=budget_manager,
                engine=engine,
                dry_run=False,
                goal_timeout=60,
            )
        return loop.time() - began, await engine.store.load_process(pid)

    elapsed, process = asyncio.run(_run())

    assert elapsed < 10
    assert process.state == ProcessState.FAILED
    assert process.properties["__error__"] == KILL_SWITCH_REASON

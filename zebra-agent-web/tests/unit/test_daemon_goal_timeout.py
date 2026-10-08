"""Daemon goals are bounded by GOAL_TIMEOUT_SECONDS (GitLab #142).

start_process() runs auto tasks inline, so before #142 a slow goal blocked the
daemon indefinitely. The GoalTracker now starts goals through
start_process_with_timeout. Uses a real engine + InMemoryStore with a slow action.
(Kill-switch cancellation is covered in test_daemon_handoff.py.)
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
from zebra_agent.scheduler import GoalScheduler
from zebra_agent.scheduler.goal_tracker import GoalTracker
from zebra_agent_web.api.daemon import _tick


class _SlowAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(30)
        return TaskResult.ok(output="too late")


async def test_slow_goal_is_failed_at_goal_timeout():
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
    budget_manager = AsyncMock()
    budget_manager.get_status = AsyncMock(
        return_value={"available": 10.0, "spent_today": 0.0, "paced_allowance": 50.0}
    )

    loop = asyncio.get_running_loop()
    began = loop.time()
    with patch("zebra_agent_web.api.kill_switch.is_halted", new=AsyncMock(return_value=False)):
        await _tick(
            scheduler=GoalScheduler(engine.store),
            budget_manager=budget_manager,
            engine=engine,
            dry_run=False,
            tracker=GoalTracker(engine, goal_timeout=0.2),
            poll_interval=0.01,
        )

    assert loop.time() - began < 5
    stored = await engine.store.load_process(process.id)
    assert stored.state == ProcessState.FAILED
    assert "Timed out after 0.2s" in stored.properties["__error__"]

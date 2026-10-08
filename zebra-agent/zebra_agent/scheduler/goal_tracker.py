"""GoalTracker — the budget daemon's view of goals it has started (#141).

``WorkflowEngine.start_process`` runs every auto task inline, so the daemon
runs it as a background task and only waits until the goal finishes or parks on
a human task. The background run is bounded by ``goal_timeout`` (#142) via
``start_process_with_timeout``. Parked goals stay tracked; each tick reconciles tracked goals that
have since reached COMPLETE/FAILED so their outcome is recorded exactly once.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from zebra.core.models import ProcessState

from zebra_agent.human_tasks import find_pending_human_task
from zebra_agent.loop import DEFAULT_GOAL_TIMEOUT

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import ProcessInstance

logger = logging.getLogger(__name__)

# Process property marking goals started by the daemon, so a restarted daemon
# can resume tracking them.
DAEMON_STARTED_KEY = "__daemon_started__"

_TERMINAL = {ProcessState.COMPLETE, ProcessState.FAILED}

# How long cancel_active waits for a goal to honour its cancel reason before
# hard-cancelling the task; the bounded start polls the reason every second.
_CANCEL_GRACE_SECONDS = 5.0

WaitOutcome = Literal["finished", "awaiting_human", "stalled", "halted"]


@dataclass
class TrackedGoal:
    """A goal the daemon started and has not yet recorded an outcome for."""

    process_id: str
    run_id: str
    task: asyncio.Task | None = None
    cancel_reason: str | None = None

    @property
    def executing(self) -> bool:
        """True while the background ``start_process`` task is still running."""
        return self.task is not None and not self.task.done()


class GoalTracker:
    """Track daemon-started goals across ticks."""

    def __init__(self, engine: WorkflowEngine, goal_timeout: float = DEFAULT_GOAL_TIMEOUT) -> None:
        self._engine = engine
        self._goal_timeout = goal_timeout
        self._goals: dict[str, TrackedGoal] = {}
        self._seeded = False

    @property
    def goals(self) -> list[TrackedGoal]:
        """Currently tracked goals."""
        return list(self._goals.values())

    async def seed(self) -> None:
        """Track RUNNING daemon-started goals left over from a previous daemon (once)."""
        if self._seeded:
            return
        self._seeded = True
        running = await self._engine.store.get_processes_by_state(
            ProcessState.RUNNING, exclude_children=True
        )
        for process in running:
            props = process.properties or {}
            if props.get(DAEMON_STARTED_KEY) and process.id not in self._goals:
                self._goals[process.id] = TrackedGoal(process.id, props.get("run_id", "-"))
                logger.info("GoalTracker: resumed tracking goal %s", process.id[:12])

    async def start(self, process: ProcessInstance) -> TrackedGoal:
        """Mark *process* as daemon-started and run it in a background task.

        The run is failed if its auto tasks exceed ``goal_timeout`` or once
        ``cancel_active`` sets the goal's ``cancel_reason`` (#142).
        """
        process.properties[DAEMON_STARTED_KEY] = True
        await self._engine.store.save_process(process)
        goal = TrackedGoal(process.id, process.properties.get("run_id", "-"))

        async def cancel_check() -> str | None:
            return goal.cancel_reason

        goal.task = asyncio.create_task(
            self._engine.start_process_with_timeout(
                process.id, self._goal_timeout, cancel_check=cancel_check
            ),
            name=f"goal-{process.id[:12]}",
        )
        self._goals[process.id] = goal
        return goal

    async def wait(
        self,
        goal: TrackedGoal,
        *,
        poll_interval: float = 1.0,
        should_stop: Callable[[], Awaitable[bool]] | None = None,
    ) -> tuple[WaitOutcome, str | None]:
        """Wait until *goal* finishes or stops making progress without a human.

        Returns:
            ``("finished", None)`` when the process is COMPLETE/FAILED;
            ``("awaiting_human", task_name)`` when a human task is pending;
            ``("stalled", None)`` when execution returned but the process is
            neither terminal nor waiting on a human (e.g. flagged for review);
            ``("halted", None)`` when *should_stop* returned True.
        """
        while True:
            if goal.task is not None and not goal.task.done():
                await asyncio.wait({goal.task}, timeout=poll_interval)

            process = await self._engine.store.load_process(goal.process_id)
            if process is None or process.state in _TERMINAL:
                return "finished", None

            pending = await find_pending_human_task(self._engine, goal.process_id)
            if pending is not None:
                return "awaiting_human", pending[1]

            if not goal.executing:
                return "stalled", None

            if should_stop is not None and await should_stop():
                return "halted", None

    async def reconcile(self) -> list[ProcessInstance]:
        """Stop tracking goals that reached COMPLETE/FAILED and return them.

        A goal whose background task crashed is kept (it may be recovered) but
        loses its task; one that never left CREATED is dropped so the queue can
        pick it up again.
        """
        finished: list[ProcessInstance] = []
        for goal in list(self._goals.values()):
            if goal.task is not None and goal.task.done():
                if not goal.task.cancelled() and goal.task.exception() is not None:
                    logger.error(
                        "Goal %s execution raised",
                        goal.process_id[:12],
                        exc_info=goal.task.exception(),
                    )
                goal.task = None

            process = await self._engine.store.load_process(goal.process_id)
            if process is None:
                del self._goals[goal.process_id]
            elif process.state in _TERMINAL:
                del self._goals[goal.process_id]
                finished.append(process)
            elif process.state == ProcessState.CREATED and goal.task is None:
                del self._goals[goal.process_id]
        return finished

    async def active_goals(self) -> list[TrackedGoal]:
        """Goals still executing in this daemon and not waiting on a human."""
        active = []
        for goal in self._goals.values():
            if (
                goal.executing
                and await find_pending_human_task(self._engine, goal.process_id) is None
            ):
                active.append(goal)
        return active

    async def cancel_active(self, reason: str) -> list[str]:
        """Cancel every active goal's execution and fail its process.

        Returns:
            Process IDs that were cancelled.
        """
        cancelled = []
        for goal in await self.active_goals():
            # The bounded start fails the process with this reason on its next poll.
            goal.cancel_reason = reason
            await asyncio.wait({goal.task}, timeout=_CANCEL_GRACE_SECONDS)
            if not goal.task.done():
                goal.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await goal.task
            goal.task = None
            try:
                process = await self._engine.store.load_process(goal.process_id)
                if process is not None and process.state not in _TERMINAL:
                    await self._engine.fail_process(goal.process_id, reason)
            except Exception:
                logger.exception("Failed to fail cancelled goal %s", goal.process_id[:12])
            del self._goals[goal.process_id]
            cancelled.append(goal.process_id)
        return cancelled

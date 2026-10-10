"""SchedulerLoop — background asyncio task that fires scheduled routines."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from zebra.core.models import ProcessState

from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import RoutineRunStore

logger = logging.getLogger(__name__)

# A routine's previous goal only blocks a new one while it is younger than this, so a
# goal parked forever (e.g. on an unanswered human task) cannot stop the routine (F155).
PENDING_GOAL_MAX_AGE = timedelta(hours=20)


class SchedulerLoop:
    """Tick-based scheduler that evaluates due routines and dispatches them.

    Each tick:
    1. Iterate registered routines.
    2. Load persisted RoutineRun (or bootstrap on first run).
    3. If now >= next_run, dispatch the routine.
    4. Persist updated last_run / next_run.

    Args:
        registry: Holds all known Routine definitions.
        store: Persists RoutineRun state across restarts.
        engine: WorkflowEngine used to create/start processes.
        budget_manager: Optional BudgetManager for budget-aware routines.
        stop_event: Set to request graceful shutdown.
        poll_interval: Seconds between ticks.
        clock: Callable returning current UTC datetime (injectable for tests).
        routines_dir: Optional path to YAML routines directory; loaded on start.
        goal_queue_tick_fn: Optional full goal-queue tick used for ``workflow: null`` routines.
        queue_goal_fn: Optional ``async fn(routine)`` that queues ``routine.goal`` as a goal
            tagged ``__routine__`` (the web daemon wires ``api.goals.queue_goal``).
    """

    def __init__(
        self,
        registry: RoutineRegistry,
        store: RoutineRunStore,
        engine,
        budget_manager=None,
        stop_event: asyncio.Event | None = None,
        poll_interval: int = 30,
        clock: Callable[[], datetime] | None = None,
        routines_dir: str | None = None,
        goal_queue_tick_fn: Callable | None = None,
        queue_goal_fn: Callable[[Routine], Awaitable[object]] | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._engine = engine
        self._budget_manager = budget_manager
        self._stop_event = stop_event or asyncio.Event()
        self._poll_interval = poll_interval
        self._clock = clock or (lambda: datetime.now(UTC))
        self._routines_dir = routines_dir
        self._goal_queue_tick_fn = goal_queue_tick_fn
        self._queue_goal_fn = queue_goal_fn

    async def run(self) -> None:
        """Run the scheduler loop until stop_event is set."""
        if self._routines_dir:
            self._registry.load_yaml_dir(self._routines_dir)
        self._registry.load_entry_points()

        logger.info(
            "SchedulerLoop started  routines=%d  poll=%ds",
            len(self._registry.all()),
            self._poll_interval,
        )

        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Error in scheduler tick")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except TimeoutError:
                pass

        logger.info("SchedulerLoop stopped.")

    async def _tick(self) -> None:
        now = self._clock()
        for routine in self._registry.all():
            await self._evaluate_routine(routine, now)

    async def _evaluate_routine(self, routine: Routine, now: datetime) -> None:
        run = await self._store.get_run(routine.name)

        if run is None:
            run = RoutineRun.initial(routine, now)

        if now < run.next_run:
            return  # not due yet

        logger.info("[scheduler:due] %s  next_run=%s", routine.name, run.next_run)

        # Budget check for budget-aware routines
        if routine.budget_aware and self._budget_manager is not None:
            status = await self._budget_manager.get_status()
            if status.get("available", 0) <= 0:
                logger.warning(
                    "[scheduler:skip] %s — budget exhausted (available=$%.4f)",
                    routine.name,
                    status.get("available", 0),
                )
                # Still advance next_run so we don't re-check every tick
                updated = run.advance(routine, now, status="budget_skip")
                await self._store.upsert_run(updated)
                return

        try:
            status = await self._dispatch(routine, now) or "ok"
            updated = run.advance(routine, now, status=status)
        except Exception:
            logger.exception("[scheduler:error] Failed to dispatch %s", routine.name)
            updated = run.advance(routine, now, status="error")

        await self._store.upsert_run(updated)

    async def _dispatch(self, routine: Routine, now: datetime) -> str | None:
        """Dispatch a due routine: queue a goal, start a workflow, or run the goal-queue tick.

        Returns a run status other than ``ok`` when the routine was deliberately skipped.
        """
        if routine.goal:
            return await self._queue_routine_goal(routine, now)

        if routine.workflow is None:
            # goal_queue_tick: use existing GoalScheduler logic
            await self._run_goal_queue_tick(routine)
            return

        # Proactive routine: create and start a new workflow process

        library = self._engine.extras.get("__workflow_library__")
        if library is None:
            logger.warning(
                "[scheduler:skip] %s — no __workflow_library__ in engine.extras", routine.name
            )
            return

        try:
            definition = library.get_workflow(routine.workflow)
        except ValueError:
            logger.warning(
                "[scheduler:skip] %s — workflow %r not found in library",
                routine.name,
                routine.workflow,
            )
            return

        properties = {"__routine__": routine.name, **routine.extra_properties}
        process = await self._engine.create_process(definition, properties=properties)
        logger.info(
            "[scheduler:dispatch] %s  workflow=%s  process=%s",
            routine.name,
            routine.workflow,
            process.id[:12],
        )
        await self._engine.start_process(process.id)

    async def _queue_routine_goal(self, routine: Routine, now: datetime) -> str | None:
        """Queue ``routine.goal`` unless a recent goal from this routine is still pending."""
        if self._queue_goal_fn is None:
            logger.warning("[scheduler:skip] %s — no queue_goal_fn configured", routine.name)
            return "skipped"

        for state in (ProcessState.CREATED, ProcessState.RUNNING):
            for process in await self._engine.store.get_processes_by_state(state):
                if (process.properties or {}).get("__routine__") != routine.name:
                    continue
                if now - process.created_at < PENDING_GOAL_MAX_AGE:
                    logger.info(
                        "[scheduler:skip] %s — goal %s still %s",
                        routine.name,
                        process.id[:12],
                        state.value,
                    )
                    return "already_queued"

        process = await self._queue_goal_fn(routine)
        logger.info(
            "[scheduler:dispatch] %s  goal queued  process=%s",
            routine.name,
            getattr(process, "id", "?")[:12],
        )
        return None

    async def _run_goal_queue_tick(self, routine: Routine) -> None:
        """Run the goal-queue daemon tick (reactive routine).

        Uses the injected ``goal_queue_tick_fn`` if provided (e.g. the full
        daemon _tick with wait-for-completion and metrics logging), otherwise
        falls back to the simple pick-and-start behaviour.
        """
        if self._goal_queue_tick_fn is not None:
            await self._goal_queue_tick_fn()
            return

        # Default: simple pick + start (used in tests / standalone)
        from zebra_agent.scheduler.goal_queue import GoalScheduler

        scheduler = GoalScheduler(self._engine.store)
        process = await scheduler.pick_next()
        if process is None:
            return

        logger.info("[scheduler:goal_queue] starting %s", process.id[:12])
        try:
            await self._engine.start_process(process.id)
        except Exception:
            logger.exception("goal_queue_tick failed to start process %s", process.id[:12])

"""Budget daemon — goal-queue execution and polling scheduler.

This module contains the core daemon logic shared by:
- The ``run_daemon`` management command (standalone process)
- The ASGI auto-start middleware (in-process background task)

``run_daemon_loop`` starts a ``SchedulerLoop`` that:
  1. Fires ``goal_queue_tick`` on every poll interval (reconciles in-flight goals,
     picks the highest-priority CREATED process, budget-checks it, runs it until it
     finishes or parks on a human task, logs cost).
  2. Fires any other routines discovered from ``fixtures/routines/*.yaml`` when due.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from zebra_agent.loop import DEFAULT_GOAL_TIMEOUT

if TYPE_CHECKING:
    from zebra_agent.scheduler.goal_tracker import GoalTracker

logger = logging.getLogger(__name__)

# Path to the built-in routine definitions relative to this file
_ROUTINES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "routines"


async def run_daemon_loop(
    stop_event: asyncio.Event,
    *,
    daily_budget: float | None = None,
    poll_interval: int | None = None,
) -> None:
    """Run the scheduler+daemon loop until *stop_event* is set.

    Parameters
    ----------
    stop_event:
        Set this event to request a graceful shutdown.
    daily_budget:
        Override the ``DAILY_BUDGET_USD`` setting.  ``None`` uses the default.
    poll_interval:
        Override the ``DAEMON_POLL_INTERVAL`` setting (seconds).  ``None``
        uses the default.
    """
    from django.conf import settings

    from zebra_agent_web.api import agent_engine
    from zebra_agent_web.api.engine import ensure_initialized as ensure_engine
    from zebra_agent_web.api.engine import get_engine

    # Initialise the full stack (Django store, agent engine, etc.)
    await agent_engine.ensure_initialized()
    await ensure_engine()

    agent_settings = getattr(settings, "ZEBRA_AGENT_SETTINGS", {})

    # Budget manager was created during agent_engine init
    budget_manager = agent_engine.get_budget_manager()

    if daily_budget is not None:
        budget_manager.daily_budget_usd = daily_budget

    if poll_interval is None:
        poll_interval = agent_settings.get("DAEMON_POLL_INTERVAL", 30)

    wf_engine = get_engine()

    from zebra_agent.scheduler.loop import SchedulerLoop
    from zebra_agent.scheduler.registry import RoutineRegistry

    from zebra_agent_web.routine_run_store import DjangoRoutineRunStore

    registry = RoutineRegistry()
    store = DjangoRoutineRunStore()

    # The goal_queue_tick_fn wraps the full _tick logic (budget check, wait,
    # metrics) so the SchedulerLoop doesn't need to know about it.
    from zebra_agent.scheduler import GoalScheduler
    from zebra_agent.scheduler.goal_tracker import GoalTracker

    goal_scheduler = GoalScheduler(wf_engine.store)
    # Each goal's auto-task chain is failed after GOAL_TIMEOUT_SECONDS (#142).
    goal_tracker = GoalTracker(
        wf_engine,
        goal_timeout=agent_settings.get("GOAL_TIMEOUT_SECONDS", DEFAULT_GOAL_TIMEOUT),
    )

    async def _goal_queue_tick_fn() -> None:
        await _tick(
            scheduler=goal_scheduler,
            budget_manager=budget_manager,
            engine=wf_engine,
            dry_run=False,
            tracker=goal_tracker,
        )

    # Routine-dispatched workflows (e.g. the 03:00 Dream Cycle) need the same
    # LLM/library context that AgentLoop.run_dream_cycle() sets; without it the
    # evaluator/optimizer fail with "No LLM provider available".
    agent_loop = agent_engine.get_agent_loop()
    routine_properties = {
        "__llm_provider_name__": agent_loop.provider_name,
        "__llm_model__": agent_loop.model,
        "__workflow_library_path__": str(agent_loop.library.library_path),
    }

    scheduler_loop = SchedulerLoop(
        registry=registry,
        store=store,
        engine=wf_engine,
        budget_manager=budget_manager,
        stop_event=stop_event,
        poll_interval=poll_interval,
        routines_dir=str(_ROUTINES_DIR),
        goal_queue_tick_fn=_goal_queue_tick_fn,
        queue_goal_fn=queue_routine_goal,
        default_properties=routine_properties,
    )

    logger.info(
        "Daemon started via SchedulerLoop  budget=$%.2f/day  poll=%ds  routines_dir=%s",
        budget_manager.daily_budget_usd,
        poll_interval,
        _ROUTINES_DIR,
    )

    # Recover any processes that were RUNNING when the daemon last stopped.
    # resume_all_processes() resets RUNNING tasks back to READY (or flags
    # non-idempotent ones for manual review) and re-drives them — which runs the
    # rest of each recovered goal inline. F129: run it as a background task so a
    # long recovered goal doesn't hold up the scheduler loop. Tasks interrupted
    # too often fail their process instead of being retried/flagged (#130).
    recovery = asyncio.create_task(
        recover_interrupted(
            wf_engine,
            max_interrupted_attempts=agent_settings.get("RECOVERY_MAX_INTERRUPTED_ATTEMPTS", 3),
        ),
        name="daemon-recovery",
    )

    try:
        await scheduler_loop.run()
    finally:
        if not recovery.done():
            recovery.cancel()

    logger.info("Daemon stopped.")


async def resolve_routine_user(username: str | None) -> int | None:
    """User id a routine's goal runs as (F155).

    *username* if given; otherwise the owner: the first active superuser, else the
    earliest-created active user (single-user installs may have no superuser, and
    service accounts such as the CI smoke user are created after the owner).

    Returns None when no such user exists — the goal still runs, but user-scoped
    steps (knowledge, values profile) skip.
    """
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(is_active=True)
    if username:
        user = await users.filter(username=username).afirst()
    else:
        user = (
            await users.filter(is_superuser=True).order_by("id").afirst()
            or await users.order_by("id").afirst()
        )
    if user is None:
        logger.warning("Routine goal: no user %r — running without a user", username or "(owner)")
        return None
    return user.id


async def queue_routine_goal(routine):
    """Queue a scheduled routine's goal through the normal goal queue (F155).

    The goal is tagged ``__routine__`` (so the scheduler does not queue it twice)
    and, when the routine names a workflow, asks the selector for it via
    ``requested_workflow``.
    """
    from zebra_agent_web.api.goals import queue_goal
    from zebra_agent_web.api.identity import goal_identity

    extra = {"__routine__": routine.name, **routine.extra_properties}
    if routine.workflow:
        extra["requested_workflow"] = routine.workflow
    return await queue_goal(
        routine.goal,
        priority=routine.goal_priority,
        user_id=await resolve_routine_user(routine.run_as),
        identity=await goal_identity(),
        extra_properties=extra,
    )


async def recover_interrupted(engine, max_interrupted_attempts: int | None = None) -> None:
    """Resume processes interrupted by the last shutdown; never raises.

    Args:
        engine: The workflow engine.
        max_interrupted_attempts: Recovery cap passed to ``resume_all_processes``
            (#130); ``None`` disables it.
    """
    try:
        resumed = await engine.resume_all_processes(
            max_interrupted_attempts=max_interrupted_attempts
        )
        if resumed:
            logger.info("Daemon startup: resumed %d interrupted process(es)", len(resumed))
    except Exception:
        logger.exception("Daemon startup: error during process recovery — continuing")


async def _tick(
    *,
    scheduler,
    budget_manager,
    engine,
    dry_run: bool,
    tracker: GoalTracker | None = None,
    poll_interval: float = 1.0,
) -> None:
    """One goal-queue iteration: reconcile, pick a goal, check budget, execute.

    The picked goal runs in a background task; the tick waits until it finishes
    or parks on a human task, then returns so a waiting goal never blocks the
    queue (#141). *tracker* carries in-flight goals between ticks; when omitted
    a fresh one is used (single-tick callers such as tests).
    """
    from zebra_agent.scheduler.goal_tracker import GoalTracker

    from zebra_agent_web.api.kill_switch import is_halted

    if tracker is None:
        tracker = GoalTracker(engine)
    await tracker.seed()

    # 0. Kill-switch guard — cancel executing goals and skip pickup while halted
    if await is_halted():
        for process_id in await tracker.cancel_active("Kill switch activated"):
            logger.warning("[daemon:halted] Kill switch active — cancelled %s", process_id[:12])
        logger.warning("[daemon:halted] Kill switch active — skipping pickup")
        return

    # 1. Record goals that finished since the last tick (e.g. after a human answered)
    for finished in await tracker.reconcile():
        _log_outcome(finished)

    # 2. Keep execution serial: don't start another goal while one is still running
    active = await tracker.active_goals()
    if active:
        logger.info("[daemon:busy] %s still executing — skipping pickup", active[0].process_id[:12])
        return

    # 3. Pick highest-priority CREATED process
    process = await scheduler.pick_next()
    if process is None:
        return  # empty queue — nothing to do

    props = process.properties or {}
    goal = props.get("goal", "(no goal)")[:80]
    priority = props.get("priority", 3)
    deadline = props.get("deadline", "none")
    run_id = props.get("run_id", "-")

    logger.info(
        "[daemon:pick] %s  run_id=%s  pri=%s  deadline=%s  goal=%s",
        process.id[:12],
        run_id,
        priority,
        deadline,
        goal,
    )

    # 4. Budget check
    status = await budget_manager.get_status()
    available = status["available"]
    logger.info(
        "[daemon:budget] spent=$%.4f  paced=$%.4f  available=$%.4f",
        status["spent_today"],
        status["paced_allowance"],
        available,
    )

    if available <= 0:
        logger.warning("[daemon:skip] Budget exhausted for this period — waiting")
        return

    if dry_run:
        logger.info("[daemon:dry-run] Would start %s", process.id[:12])
        return

    # 5. Start the goal in the background and wait until it finishes or needs a human
    logger.info("[daemon:start] Starting %s  run_id=%s...", process.id[:12], run_id)
    tracked = await tracker.start(process)
    outcome, task_name = await tracker.wait(
        tracked, poll_interval=poll_interval, should_stop=is_halted
    )

    if outcome == "halted":
        logger.warning(
            "[daemon:halted] Kill switch set mid-flight — cancelling %s", process.id[:12]
        )
        await tracker.cancel_active("Kill switch activated")
    elif outcome == "awaiting_human":
        logger.info(
            "[daemon:await] %s  run_id=%s  waiting on human task %r — moving on",
            process.id[:12],
            run_id,
            task_name,
        )
    elif outcome == "stalled":
        logger.warning(
            "[daemon:stalled] %s  run_id=%s  not running and not awaiting a human — "
            "tracking until it terminates",
            process.id[:12],
            run_id,
        )
    else:
        for finished in await tracker.reconcile():
            _log_outcome(finished)


def _log_outcome(process) -> None:
    """Log a finished goal's outcome and update the goals_completed metric."""
    from zebra.core.models import ProcessState

    from zebra_agent_web.api.metrics import goals_completed

    props = process.properties or {}
    run_id = props.get("run_id", "-")
    if process.state == ProcessState.COMPLETE:
        logger.info(
            "[daemon:done] %s  run_id=%s  completed  cost=$%.6f  tokens=%s",
            process.id[:12],
            run_id,
            props.get("__total_cost__", 0.0),
            props.get("__total_tokens__", 0),
        )
        goals_completed.labels(status="success").inc()
    else:
        logger.error(
            "[daemon:fail] %s  run_id=%s  failed: %s",
            process.id[:12],
            run_id,
            props.get("__error__", "unknown"),
        )
        goals_completed.labels(status="failed").inc()

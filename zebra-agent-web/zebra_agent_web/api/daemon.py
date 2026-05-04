"""Budget daemon — goal-queue execution and polling scheduler.

This module contains the core daemon logic shared by:
- The ``run_daemon`` management command (standalone process)
- The ASGI auto-start middleware (in-process background task)

``run_daemon_loop`` starts a ``SchedulerLoop`` that:
  1. Fires ``goal_queue_tick`` on every poll interval (picks the highest-priority
     CREATED process, budget-checks it, starts it, waits for completion, logs cost).
  2. Fires any other routines discovered from ``fixtures/routines/*.yaml`` when due.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

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

    goal_scheduler = GoalScheduler(wf_engine.store)

    async def _goal_queue_tick_fn() -> None:
        await _tick(
            scheduler=goal_scheduler,
            budget_manager=budget_manager,
            engine=wf_engine,
            dry_run=False,
        )

    scheduler_loop = SchedulerLoop(
        registry=registry,
        store=store,
        engine=wf_engine,
        budget_manager=budget_manager,
        stop_event=stop_event,
        poll_interval=poll_interval,
        routines_dir=str(_ROUTINES_DIR),
        goal_queue_tick_fn=_goal_queue_tick_fn,
    )

    logger.info(
        "Daemon started via SchedulerLoop  budget=$%.2f/day  poll=%ds  routines_dir=%s",
        budget_manager.daily_budget_usd,
        poll_interval,
        _ROUTINES_DIR,
    )

    await scheduler_loop.run()

    logger.info("Daemon stopped.")


async def _tick(
    *,
    scheduler,
    budget_manager,
    engine,
    dry_run: bool,
) -> None:
    """One goal-queue iteration: pick a goal, check budget, execute, log cost."""
    from zebra.core.models import ProcessState

    from zebra_agent_web.api.kill_switch import is_halted

    # 0. Kill-switch guard — skip pickup while system is halted
    if await is_halted():
        logger.warning("[daemon:halted] Kill switch active — skipping pickup")
        return

    # 1. Pick highest-priority CREATED process
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

    # 2. Budget check
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

    # 3. Start the process
    logger.info("[daemon:start] Starting %s  run_id=%s...", process.id[:12], run_id)
    try:
        await engine.start_process(process.id)
    except Exception:
        logger.exception("Failed to start process %s", process.id[:12])
        return

    # 4. Poll until completion (with a generous timeout)
    max_wait = 600  # 10 minutes per goal
    waited = 0.0
    poll_sec = 2.0

    while waited < max_wait:
        if await is_halted():
            logger.warning(
                "[daemon:halted] Kill switch set mid-flight — cancelling %s", process.id[:12]
            )
            try:
                await engine.fail_process(process.id, "Kill switch activated")
            except Exception:
                logger.exception("Failed to cancel in-flight process %s", process.id[:12])
            return
        process = await engine.store.load_process(process.id)
        if process.state in (ProcessState.COMPLETE, ProcessState.FAILED):
            break
        await asyncio.sleep(poll_sec)
        waited += poll_sec

    # 5. Log outcome and update metrics
    from zebra_agent_web.api.metrics import goals_completed

    if process.state == ProcessState.COMPLETE:
        cost = (process.properties or {}).get("__total_cost__", 0.0)
        tokens = (process.properties or {}).get("__total_tokens__", 0)
        logger.info(
            "[daemon:done] %s  run_id=%s  completed  cost=$%.6f  tokens=%s",
            process.id[:12],
            run_id,
            cost,
            tokens,
        )
        goals_completed.labels(status="success").inc()
    elif process.state == ProcessState.FAILED:
        error = (process.properties or {}).get("__error__", "unknown")
        logger.error("[daemon:fail] %s  run_id=%s  failed: %s", process.id[:12], run_id, error)
        goals_completed.labels(status="failed").inc()
    else:
        logger.warning(
            "[daemon:timeout] %s  run_id=%s  still %s after %ss — will check again next tick",
            process.id[:12],
            run_id,
            process.state.value,
            max_wait,
        )
        goals_completed.labels(status="timeout").inc()

"""Reusable budget daemon loop for queued goal execution.

This module contains the core daemon logic shared by:
- The ``run_daemon`` management command (standalone process)
- The ASGI auto-start middleware (in-process background task)

The daemon continuously picks the highest-priority CREATED process,
checks the daily budget, starts it, waits for completion, and repeats.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_daemon_loop(
    stop_event: asyncio.Event,
    *,
    daily_budget: float | None = None,
    poll_interval: int | None = None,
) -> None:
    """Run the budget daemon loop until *stop_event* is set.

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

    from zebra_agent.scheduler import GoalScheduler

    wf_engine = get_engine()
    scheduler = GoalScheduler(wf_engine.store)

    logger.info(
        "Budget daemon started  budget=$%.2f/day  poll=%ds",
        budget_manager.daily_budget_usd,
        poll_interval,
    )

    while not stop_event.is_set():
        try:
            await _tick(
                scheduler=scheduler,
                budget_manager=budget_manager,
                engine=wf_engine,
                dry_run=False,
            )
        except Exception:
            logger.exception("Error in daemon tick")

        # Sleep (interruptible by stop_event)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            break  # stop_event was set
        except asyncio.TimeoutError:
            pass  # normal — just continue the loop

    logger.info("Budget daemon stopped.")


async def _tick(
    *,
    scheduler,
    budget_manager,
    engine,
    dry_run: bool,
) -> None:
    """One iteration: pick a goal, check budget, execute, log cost."""
    from zebra.core.models import ProcessState

    # 1. Pick highest-priority CREATED process
    process = await scheduler.pick_next()
    if process is None:
        return  # empty queue — nothing to do

    props = process.properties or {}
    goal = props.get("goal", "(no goal)")[:80]
    priority = props.get("priority", 3)
    deadline = props.get("deadline", "none")

    logger.info(
        "[daemon:pick] %s  pri=%s  deadline=%s  goal=%s",
        process.id[:12],
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
    logger.info("[daemon:start] Starting %s...", process.id[:12])
    try:
        await engine.start_process(process.id)
    except Exception as e:
        logger.exception("Failed to start process %s", process.id[:12])
        return

    # 4. Poll until completion (with a generous timeout)
    max_wait = 600  # 10 minutes per goal
    waited = 0.0
    poll_sec = 2.0

    while waited < max_wait:
        process = await engine.store.load_process(process.id)
        if process.state in (ProcessState.COMPLETE, ProcessState.FAILED):
            break
        await asyncio.sleep(poll_sec)
        waited += poll_sec

    # 5. Log outcome
    if process.state == ProcessState.COMPLETE:
        cost = (process.properties or {}).get("__total_cost__", 0.0)
        tokens = (process.properties or {}).get("__total_tokens__", 0)
        logger.info(
            "[daemon:done] %s completed  cost=$%.6f  tokens=%s",
            process.id[:12],
            cost,
            tokens,
        )
    elif process.state == ProcessState.FAILED:
        error = (process.properties or {}).get("__error__", "unknown")
        logger.error("[daemon:fail] %s failed: %s", process.id[:12], error)
    else:
        logger.warning(
            "[daemon:timeout] %s still %s after %ss — will check again next tick",
            process.id[:12],
            process.state.value,
            max_wait,
        )

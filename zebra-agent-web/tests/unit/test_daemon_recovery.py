"""F129: daemon startup recovery must not block the scheduler loop.

``resume_all_processes`` re-drives every recovered goal inline, which can take
as long as the goal itself; the daemon therefore runs it as a background task.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from zebra_agent_web.api.daemon import recover_interrupted, run_daemon_loop


async def test_scheduler_loop_starts_while_recovery_still_running():
    recovery_started = asyncio.Event()
    recovery_cancelled = asyncio.Event()
    loop_ran_during_recovery: list[bool] = []

    async def slow_resume():
        recovery_started.set()
        try:
            await asyncio.Event().wait()  # a long recovered goal
        except asyncio.CancelledError:
            recovery_cancelled.set()
            raise

    engine = MagicMock()
    engine.resume_all_processes = slow_resume

    class FakeSchedulerLoop:
        def __init__(self, **kwargs):
            pass

        async def run(self):
            await asyncio.wait_for(recovery_started.wait(), timeout=2)
            loop_ran_during_recovery.append(not recovery_cancelled.is_set())

    with (
        patch("zebra_agent_web.api.agent_engine.ensure_initialized", AsyncMock()),
        patch("zebra_agent_web.api.agent_engine.get_budget_manager", MagicMock()),
        patch("zebra_agent_web.api.engine.ensure_initialized", AsyncMock()),
        patch("zebra_agent_web.api.engine.get_engine", return_value=engine),
        patch("zebra_agent.scheduler.loop.SchedulerLoop", FakeSchedulerLoop),
        patch("zebra_agent_web.routine_run_store.DjangoRoutineRunStore", MagicMock()),
    ):
        await asyncio.wait_for(run_daemon_loop(asyncio.Event(), poll_interval=1), timeout=3)

    assert loop_ran_during_recovery == [True]
    # Shutdown cancels a recovery that is still in flight.
    await asyncio.wait_for(recovery_cancelled.wait(), timeout=1)


async def test_recover_interrupted_swallows_errors():
    engine = MagicMock()
    engine.resume_all_processes = AsyncMock(side_effect=RuntimeError("boom"))

    await recover_interrupted(engine)  # must not raise

    engine.resume_all_processes.assert_awaited_once()

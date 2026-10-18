"""Replay a finished process from its recording (#170).

``replay_process`` creates a replay with ``WorkflowEngine.create_replay``, runs
it, and reports where it ended, like ``direct_run.workflow_status``, plus what it
replayed and what it spent. Used by ``manage.py replay_process`` and the step
trace's Replay form.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zebra.core.replay import REPLAY_KEY

from zebra_agent.direct_run import workflow_status

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import ProcessDefinition


async def replay_process(
    engine: WorkflowEngine,
    process_id: str,
    *,
    live: list[str] | None = None,
    definition: ProcessDefinition | None = None,
    continue_live: bool = False,
    timeout: float = 900.0,
) -> dict[str, Any]:
    """Replay *process_id* and return its status.

    Args:
        engine: The workflow engine (its extras serve any live steps).
        process_id: A COMPLETE or FAILED process with a step journal.
        live: Step ids to run live instead of replaying.
        definition: Replacement definition; its changed steps run live.
        continue_live: Run steps the recording has no run of live.
        timeout: Seconds the replay's auto steps may run.

    Returns:
        ``workflow_status`` for the replay plus ``replay_of``, ``live`` and ``cost``.

    Raises:
        ReplayError: If the process cannot be replayed.
    """
    replayed = await engine.create_replay(
        process_id, live=live, definition=definition, continue_live=continue_live
    )
    await engine.start_process_with_timeout(replayed.id, timeout)
    return await replay_status(engine, replayed.id)


async def replay_status(engine: WorkflowEngine, process_id: str) -> dict[str, Any]:
    """``workflow_status`` of a replay, with what it replays and what it spent."""
    status = await workflow_status(engine, process_id)
    process = await engine.store.load_process(process_id)
    props = process.properties if process else {}
    marker = props.get(REPLAY_KEY) or {}
    status.update(
        replay_of=marker.get("of"),
        live=marker.get("live", []),
        cost=props.get("__total_cost__", 0.0),
    )
    return status

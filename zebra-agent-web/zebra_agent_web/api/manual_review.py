"""Manual review of tasks flagged by engine recovery (#130).

``WorkflowEngine.resume_all_processes`` leaves interrupted non-idempotent tasks
RUNNING with ``__requires_manual_review__`` set. This module finds those tasks
for the web UI / REST API and lets a human either retry the task or fail the run.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from zebra.core.engine import MANUAL_REVIEW_FLAG, WorkflowEngine
from zebra.core.exceptions import InvalidStateTransitionError, TaskNotFoundError
from zebra.core.models import ProcessState, TaskInstance, TaskState
from zebra.storage.base import StateStore

logger = logging.getLogger(__name__)

_TERMINAL = {ProcessState.COMPLETE, ProcessState.FAILED}

# Task IDs whose retry is in progress in this server process (shared by the
# ASGI loop and DRF worker threads, hence the lock).
_in_flight: set[str] = set()
_in_flight_guard = threading.Lock()


async def find_review_tasks(store: StateStore, run_id: str | None = None) -> list[dict]:
    """Return tasks flagged for manual review, optionally only those of *run_id*.

    Each task's run is resolved by walking up the process tree to the first
    process carrying a ``run_id`` property.
    """
    flagged = [t for t in await store.get_running_tasks() if t.properties.get(MANUAL_REVIEW_FLAG)]
    results = []
    for task in flagged:
        process = await store.load_process(task.process_id)
        if process is None:
            continue
        definition = await store.load_definition(process.definition_id)
        task_def = definition.tasks.get(task.task_definition_id) if definition else None

        owner, seen = process, set()
        while owner and not (owner.properties or {}).get("run_id") and owner.id not in seen:
            seen.add(owner.id)
            owner = (
                await store.load_process(owner.parent_process_id)
                if owner.parent_process_id
                else None
            )
        task_run_id = (owner.properties or {}).get("run_id") if owner else None
        if run_id is not None and task_run_id != run_id:
            continue

        results.append(
            {
                "id": task.id,
                "task_name": task_def.name if task_def else task.task_definition_id,
                "task_definition_id": task.task_definition_id,
                "process_id": task.process_id,
                "run_id": task_run_id,
                "execution_attempt": task.execution_attempt,
                "flagged_at": task.updated_at,
            }
        )
    return results


async def _load_flagged(wf_engine: WorkflowEngine, task_id: str) -> TaskInstance:
    task = await wf_engine.store.load_task(task_id)
    if task is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    if task.state != TaskState.RUNNING or not task.properties.get(MANUAL_REVIEW_FLAG):
        raise InvalidStateTransitionError(f"Task {task_id} is not awaiting manual review")
    return task


async def retry_review_task(wf_engine: WorkflowEngine, task_id: str) -> TaskInstance:
    """Reset a flagged task to READY and re-run it in the background.

    The reset happens synchronously so callers get errors immediately; the
    (possibly long) re-execution runs on a background thread. A task already
    being retried by this server is rejected, so a double-click can't run its
    side effects twice.
    """
    with _in_flight_guard:
        if task_id in _in_flight:
            raise InvalidStateTransitionError(f"Task {task_id} is already being retried")
        _in_flight.add(task_id)
    try:
        task = await wf_engine.retry_task(task_id, execute=False)
    except BaseException:
        _in_flight.discard(task_id)
        raise
    _run_in_background(wf_engine, task.id)
    return task


async def fail_review_task(
    wf_engine: WorkflowEngine, task_id: str, reason: str | None = None
) -> list[str]:
    """Fail the run owning a flagged task.

    The task's process and every non-terminal ancestor are failed (an
    ancestor's ``execute_workflow`` task would otherwise wait forever on the
    failed child).

    Returns:
        IDs of the processes that were failed.
    """
    task = await _load_flagged(wf_engine, task_id)
    reason = reason or (
        f"Task {task.task_definition_id} ({task.id}) was failed by a user after manual "
        "review of an interrupted run"
    )
    failed: list[str] = []
    process_id: str | None = task.process_id
    seen: set[str] = set()
    while process_id and process_id not in seen:
        seen.add(process_id)
        process = await wf_engine.store.load_process(process_id)
        if process is None:
            break
        if process.state not in _TERMINAL:
            await wf_engine.fail_process(process.id, reason)
            failed.append(process.id)
        process_id = process.parent_process_id
    logger.info("Manual review failed task %s; failed processes %s", task_id, failed)
    return failed


def _run_in_background(wf_engine: WorkflowEngine, task_id: str) -> None:
    """Re-execute a reset task on a daemon thread with its own event loop.

    Mirrors the REST goal runner: a fresh loop avoids blocking (or deadlocking)
    the ASGI event loop while the task's action runs.
    """

    def _thread() -> None:
        try:
            asyncio.run(wf_engine.transition_task(task_id))
        except Exception:
            logger.exception("Background retry of task %s failed", task_id)
        finally:
            _in_flight.discard(task_id)

    threading.Thread(target=_thread, daemon=True, name=f"retry-{task_id[:8]}").start()

"""Detect goals that are parked waiting on a human (#141).

A goal is "awaiting a human" when its process, or any RUNNING descendant
process (e.g. the child spawned by ``execute_goal_workflow``), has a READY task
whose definition is ``auto: false``. Callers use this to stop waiting on such a
goal instead of treating the wait as a timeout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from zebra.core.models import ProcessState, TaskState

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import ProcessInstance, TaskInstance


async def find_pending_human_task(
    engine: WorkflowEngine, process_id: str
) -> tuple[TaskInstance, str] | None:
    """Return the first pending human task in a process tree, or None.

    Args:
        engine: The workflow engine.
        process_id: The root process to search from.

    Returns:
        ``(task, task_name)`` for the first READY ``auto: false`` task found in
        the process or its RUNNING descendants, else ``None``.
    """
    store = engine.store
    running: list[ProcessInstance] | None = None
    to_visit = [process_id]
    seen: set[str] = set()

    while to_visit:
        pid = to_visit.pop()
        if pid in seen:
            continue
        seen.add(pid)

        process = await store.load_process(pid)
        if process is None:
            continue
        definition = await store.load_definition(process.definition_id)
        if definition is not None:
            for task in await store.load_tasks_for_process(pid):
                if task.state != TaskState.READY:
                    continue
                task_def = definition.tasks.get(task.task_definition_id)
                if task_def is not None and not task_def.auto:
                    return task, task_def.name

        if running is None:
            running = await store.get_processes_by_state(ProcessState.RUNNING)
        to_visit.extend(p.id for p in running if p.parent_process_id == pid)

    return None

"""The Tasks inbox (#217): everything waiting on a human, from one read model.

``inbox_items`` feeds the ``/tasks/`` page, the nav needs-you badge and the
dashboard Needs-you strip, so all three agree. An item is either a READY human
(``auto: false``) task on an unfinished process, or a task recovery flagged for
manual review (#130).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from zebra.core.models import ProcessInstance, ProcessState
from zebra.forms import resolve_task_schema
from zebra.storage.base import StateStore

from zebra_agent_web.api import manual_review

logger = logging.getLogger(__name__)

_FINISHED = {ProcessState.COMPLETE, ProcessState.FAILED}


class _Lookup:
    """Per-call cache of processes and definitions, and root-goal resolution."""

    def __init__(self, store: StateStore) -> None:
        self._store = store
        self._processes: dict[str, ProcessInstance | None] = {}
        self._definitions: dict[str, object] = {}

    async def process(self, process_id: str | None) -> ProcessInstance | None:
        if process_id is None:
            return None
        if process_id not in self._processes:
            self._processes[process_id] = await self._store.load_process(process_id)
        return self._processes[process_id]

    async def definition(self, definition_id: str):
        if definition_id not in self._definitions:
            self._definitions[definition_id] = await self._store.load_definition(definition_id)
        return self._definitions[definition_id]

    async def context(self, process: ProcessInstance) -> dict:
        """Goal, run and workflow of the top-level process that owns *process*."""
        run_id = None
        root, seen = process, set()
        while True:
            run_id = run_id or (root.properties or {}).get("run_id")
            parent = await self.process(root.parent_process_id)
            if parent is None or parent.id in seen:
                break
            seen.add(root.id)
            root = parent
        props = root.properties or {}
        definition = await self.definition(root.definition_id)
        workflow = props.get("__workflow_name__") or (
            definition.name if definition else root.definition_id
        )
        return {
            "root_process_id": root.id,
            "run_id": run_id,
            "goal": props.get("goal") or workflow,
            "workflow_name": workflow,
        }


async def inbox_items(store: StateStore) -> list[dict]:
    """Return every item waiting on a human, oldest first.

    Each item has ``id``, ``kind`` (``"human"`` or ``"review"``), ``task_name``,
    ``title`` (form title, human items only), ``process_id``, ``root_process_id``,
    ``run_id``, ``goal``, ``workflow_name`` and ``waiting_since``; review items
    also have ``execution_attempt``.
    """
    lookup = _Lookup(store)
    items: list[dict] = []

    for task in await store.get_ready_tasks():
        process = await lookup.process(task.process_id)
        if process is None or process.state in _FINISHED:
            continue
        definition = await lookup.definition(process.definition_id)
        task_def = definition.tasks.get(task.task_definition_id) if definition else None
        if task_def is None or task_def.auto:
            continue
        schema = resolve_task_schema(task_def.properties.get("schema"), process.properties or {})
        items.append(
            {
                "id": task.id,
                "kind": "human",
                "task_name": task_def.name,
                "title": (schema or {}).get("title", ""),
                "process_id": process.id,
                "waiting_since": task.created_at,
                **await lookup.context(process),
            }
        )

    for review in await manual_review.find_review_tasks(store):
        process = await lookup.process(review["process_id"])
        if process is None:
            continue
        items.append(
            {
                "id": review["id"],
                "kind": "review",
                "task_name": review["task_name"],
                "title": "",
                "process_id": review["process_id"],
                "waiting_since": review["flagged_at"],
                "execution_attempt": review["execution_attempt"],
                **await lookup.context(process),
            }
        )

    items.sort(key=lambda i: _timestamp(i["waiting_since"]))
    return items


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()

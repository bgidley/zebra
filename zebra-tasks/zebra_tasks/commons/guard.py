"""Where Commons-internal actions may run, and the evidence they check (#230).

``commons_adopt`` writes the library and ``commons_supervised_run`` starts a supervised
workflow. Both are registered like every other action, so any workflow could name
them. They must not trust process properties (any task with an ``output_key`` can
write those), so they check:

- **the running definition**: ``commons_adopt`` only inside the shipped, protected
  *Commons Import* workflow; ``commons_offer_record`` and ``commons_publish`` (#231) only
  inside the shipped *Commons Offer*; ``commons_supervised_run`` only inside the generated
  *Supervised run* wrapper for the workflow it starts. Compared by executable shape
  (tasks, routings, construct / destruct actions), not by name.
- **the step journal** (#184): which tasks completed in this process and which route
  they chose, and what a human task's completion wrote. The engine writes it; a task
  cannot.

Generated workflows (creator, variant creator, optimizer) and imported ones may not
use ``COMMONS_INTERNAL_ACTIONS`` at all.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any

from zebra.core.models import ProcessDefinition, ProcessEvent, ProcessEventKind
from zebra.definitions.loader import load_definition_from_yaml

from zebra_tasks.agent.definition_actions import DefinedAction, definition_actions

logger = logging.getLogger(__name__)

#: Plumbing of the Commons system workflows: never in a generated or imported workflow.
COMMONS_INTERNAL_ACTIONS = frozenset(
    {
        "commons_adopt",
        "commons_supervised_run",
        "commons_judge_import",
        "commons_import_review",
        "commons_record_import",
        "commons_attest_import",  # #232
        # Commons Offer (#231)
        "commons_prepare_offer",
        "commons_offer_route",
        "commons_offer_record",
        "commons_publish",
        "commons_record_offer",
        "commons_dream",  # #235: the dream cycle's Commons step
    }
)
IMPORT_WORKFLOW_FILE = "commons_import.yaml"
OFFER_WORKFLOW_FILE = "commons_offer.yaml"


def internal_actions_used(definition: ProcessDefinition) -> list[DefinedAction]:
    """Every Commons-internal action *definition* runs (task or construct / destruct)."""
    return [d for d in definition_actions(definition) if d.action in COMMONS_INTERNAL_ACTIONS]


def executable_shape(definition: ProcessDefinition) -> dict[str, Any]:
    """What the engine runs: tasks, routings, entry and process-level hooks.

    Leaves out the id, name, version and metadata properties, which the library
    stamps (``c:`` ids, ``commons`` block) without changing what runs.
    """
    dumped = definition.model_dump(mode="json")
    return {
        key: dumped.get(key)
        for key in ("first_task_id", "tasks", "routings", "construct_action", "destruct_action")
    }


@functools.cache
def _shipped_workflow_text(filename: str) -> str | None:
    from zebra_agent.library import BUILTIN_WORKFLOWS_DIR

    path = Path(BUILTIN_WORKFLOWS_DIR) / filename
    try:
        return path.read_text()
    except OSError as e:
        logger.error("Cannot read the shipped workflow %s: %s", path, e)
        return None


def is_shipped_workflow(definition: ProcessDefinition, filename: str) -> bool:
    """Whether *definition* runs exactly the shipped built-in workflow *filename*."""
    text = _shipped_workflow_text(filename)
    if text is None:
        return False
    try:
        shipped = load_definition_from_yaml(text)
    except Exception as e:  # noqa: BLE001 - an unreadable original fails closed
        logger.error("The shipped workflow %s does not load: %s", filename, e)
        return False
    return executable_shape(definition) == executable_shape(shipped)


def is_import_workflow(definition: ProcessDefinition) -> bool:
    """Whether *definition* runs exactly the shipped *Commons Import* workflow."""
    return is_shipped_workflow(definition, IMPORT_WORKFLOW_FILE)


def is_offer_workflow(definition: ProcessDefinition) -> bool:
    """Whether *definition* runs exactly the shipped *Commons Offer* workflow (#231)."""
    return is_shipped_workflow(definition, OFFER_WORKFLOW_FILE)


async def completed_steps(context: Any) -> dict[str, ProcessEvent]:
    """The latest ``task_completed`` journal event per task definition of this process.

    Fails closed: an unreadable journal yields nothing.
    """
    try:
        events = await context.store.load_process_events([context.process.id])
    except Exception as e:  # noqa: BLE001
        logger.warning("Cannot read the step journal of %s: %s", context.process.id, e)
        return {}
    steps: dict[str, ProcessEvent] = {}
    for event in sorted(events, key=lambda e: e.timestamp):
        if (
            event.process_id == context.process.id
            and event.kind == ProcessEventKind.TASK_COMPLETED
            and event.task_definition_id
        ):
            steps[event.task_definition_id] = event
    return steps


def human_answer(steps: dict[str, ProcessEvent], task_id: str) -> dict[str, Any] | None:
    """What completing human task *task_id* wrote (``__task_output_<id>``), per the journal."""
    event = steps.get(task_id)
    if event is None:
        return None
    answer = event.changed.get(f"__task_output_{task_id}")
    return answer if isinstance(answer, dict) else None

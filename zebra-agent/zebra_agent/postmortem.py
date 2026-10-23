"""Start postmortems for incidents the Agent Main Loop could not reflect on itself (#175).

A failed goal run writes its own postmortem inside the Agent Main Loop
(``write_postmortem`` step). Two incidents never reach that step:

- a goal stopped by the goal timeout (#142) or a crash ends FAILED part-way, and
- a run the user later rates 1 or 2 already finished.

For those, :func:`start_postmortem` runs the one-task *Postmortem* system workflow
with the run's details, so the lesson is written and costed like any process.
"""

from __future__ import annotations

import logging
from typing import Any

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessInstance, ProcessState

from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

POSTMORTEM_WORKFLOW = "Postmortem"
MAIN_LOOP_WORKFLOW = "Agent Main Loop"
POSTMORTEM_TASK_OUTPUT = "__task_output_write_postmortem"

# Ratings at or below this start a low_rating postmortem.
LOW_RATING_MAX = 2

# Goals failed for these reasons were stopped on purpose; there is nothing to learn.
_DELIBERATE_STOPS = ("Kill switch activated",)

# Process properties carried onto the Postmortem process: who the goal was for
# (journal ownership, #151) and the model tier to use.
_CARRIED_KEYS = (
    "__user_id__",
    "__user_display_name__",
    "__user_identity_id__",
    "__llm_model__",
)


async def needs_failure_postmortem(engine: WorkflowEngine, process: ProcessInstance) -> bool:
    """Whether a finished process is an Agent Main Loop goal that failed unreflected.

    True for a FAILED Agent Main Loop process that never ran its
    ``write_postmortem`` step (a timeout or crash) and was not stopped on purpose.
    """
    if process.state != ProcessState.FAILED:
        return False
    props = process.properties or {}
    if POSTMORTEM_TASK_OUTPUT in props or not props.get("goal"):
        return False
    error = str(props.get("__error__") or "")
    if any(reason in error for reason in _DELIBERATE_STOPS):
        return False
    definition = await engine.store.load_definition(process.definition_id)
    return definition is not None and definition.name == MAIN_LOOP_WORKFLOW


async def start_postmortem(
    engine: WorkflowEngine,
    library: WorkflowLibrary,
    *,
    trigger: str,
    goal: str,
    run_id: str = "",
    workflow_name: str = "",
    error: str = "",
    rating: int | None = None,
    user_feedback: str = "",
    source_properties: dict[str, Any] | None = None,
) -> str | None:
    """Run the *Postmortem* workflow for one incident and return its process id.

    Never raises: a postmortem is advisory, so failures are logged and None
    returned.

    Args:
        engine: The workflow engine (with the memory store in its extras).
        library: Workflow library holding the *Postmortem* system workflow.
        trigger: ``timeout``, ``failure`` or ``low_rating``.
        goal: The run's goal.
        run_id: The run the postmortem is about (one postmortem per run).
        workflow_name: The goal workflow that ran, if known.
        error: The run's error, if any.
        rating: The user's rating (``low_rating``).
        user_feedback: The user's feedback on the run.
        source_properties: The incident process's properties; its user identity,
            provider and ``__task_executions__`` are carried over.
    """
    source = source_properties or {}
    properties: dict[str, Any] = {
        "postmortem_trigger": trigger,
        "goal": goal,
        "run_id": run_id,
        "workflow_name": workflow_name,
        "error": error,
        "rating": rating if rating is not None else "",
        "user_feedback": user_feedback,
        "__task_executions__": source.get("__task_executions__", []),
    }
    properties.update({k: source[k] for k in _CARRIED_KEYS if source.get(k) is not None})
    try:
        definition = library.get_workflow(POSTMORTEM_WORKFLOW)
        process = await engine.create_process(definition, properties=properties)
        await engine.start_process(process.id)
    except Exception as e:  # noqa: BLE001 - a postmortem must never break its caller
        logger.warning("Could not run a %s postmortem for run %s: %s", trigger, run_id, e)
        return None
    logger.info("Ran a %s postmortem for run %s (process %s)", trigger, run_id, process.id[:12])
    return process.id


def unreflected_trigger(error: str) -> str:
    """The trigger for a goal that failed before it could reflect.

    ``timeout`` when the goal timeout stopped it (the engine's "Timed out after
    Ns", the loop's "Agent loop timed out"), else ``failure``: a crash part-way
    is not a timeout (#199).
    """
    return "timeout" if "timed out" in error.lower() else "failure"


async def postmortem_failed_goal(
    engine: WorkflowEngine, library: WorkflowLibrary, process: ProcessInstance
) -> str | None:
    """Start a postmortem for a goal that failed before it could reflect.

    The trigger is ``timeout`` or ``failure`` (:func:`unreflected_trigger`).

    Returns:
        The Postmortem process id, or None when none was needed or it failed.
    """
    try:
        if not await needs_failure_postmortem(engine, process):
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Postmortem check failed for %s: %s", process.id[:12], e)
        return None
    props = process.properties or {}
    error = str(props.get("__error__") or "")
    return await start_postmortem(
        engine,
        library,
        trigger=unreflected_trigger(error),
        goal=str(props.get("goal", "")),
        run_id=str(props.get("run_id", "")),
        workflow_name=str(props.get("workflow_name", "")),
        error=error,
        source_properties=props,
    )

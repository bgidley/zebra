"""Run a named workflow directly, outside the Agent Main Loop (#190).

The delivery process runs the *Outcome Review* workflow with structured inputs
and no workflow selection. ``run_named_workflow`` creates and starts it;
``workflow_status`` reports where a process is: ``complete`` (with the
workflow's ``result_key`` output), ``awaiting_input`` (with the human task id),
``failed`` or ``running``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from zebra.core.models import ProcessState

from zebra_agent.human_tasks import find_pending_human_task

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine

    from zebra_agent.library import WorkflowLibrary


class DirectRunError(Exception):
    """Raised when a workflow cannot be started (unknown name, missing inputs)."""


async def run_named_workflow(
    engine: WorkflowEngine,
    library: WorkflowLibrary,
    name: str,
    inputs: dict[str, Any],
    *,
    model: str | None = None,
    timeout: float = 900.0,
) -> dict[str, Any]:
    """Create and start workflow ``name`` with ``inputs`` as process properties.

    Args:
        engine: The workflow engine (its extras carry the stores and library).
        library: Workflow library to load ``name`` from.
        name: Workflow name.
        inputs: Initial properties; must cover the workflow's required ``inputs``.
        model: Model tier for the run (low / medium / high / max).
        timeout: Seconds the inline auto-task chain may run (#142).

    Returns:
        The ``workflow_status`` dict for the new process.

    Raises:
        DirectRunError: If the workflow is unknown or a required input is missing.
    """
    try:
        definition = library.get_workflow(name)
    except Exception as e:
        raise DirectRunError(f"No workflow named '{name}'") from e

    info = next((w for w in await library.list_workflows() if w.name == name), None)
    required = ((info.inputs if info else None) or {}).get("required") or []
    missing = [key for key in required if inputs.get(key) in (None, "")]
    if missing:
        raise DirectRunError(f"Missing required inputs: {', '.join(missing)}")

    run_id = str(uuid.uuid4())
    properties = {
        "goal": inputs.get("goal") or name,
        **inputs,
        "run_id": run_id,
        "workflow_name": name,
        "__llm_model__": model,
    }
    process = await engine.create_process(definition, properties=properties)
    await engine.start_process_with_timeout(process.id, timeout)
    return await workflow_status(engine, process.id)


async def workflow_status(engine: WorkflowEngine, process_id: str) -> dict[str, Any]:
    """Report the state of a directly-run process."""
    process = await engine.store.load_process(process_id)
    if process is None:
        return {"status": "failed", "process_id": process_id, "error": "No such process"}

    props = process.properties or {}
    status: dict[str, Any] = {
        "status": "running",
        "process_id": process.id,
        "run_id": props.get("run_id"),
        "task_id": None,
        "output": None,
        "error": None,
    }
    if process.state == ProcessState.COMPLETE:
        definition = await engine.store.load_definition(process.definition_id)
        result_key = (definition.properties.get("result_key") if definition else None) or (
            "__output__"
        )
        status.update(status="complete", output=props.get(result_key))
    elif process.state == ProcessState.FAILED:
        status.update(status="failed", error=str(props.get("__error__") or "Process failed"))
    else:
        pending = await find_pending_human_task(engine, process.id)
        if pending is not None:
            task, task_name = pending
            status.update(status="awaiting_input", task_id=task.id, task_name=task_name)
    return status

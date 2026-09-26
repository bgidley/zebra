"""Follow-up goal support (F116).

A goal can extend a previous completed run. Entry points store a compact
summary of that run in the ``previous_run_context`` process property; agent
actions call :func:`with_previous_run` so every step that reasons about the
goal (ethics gate, selector, creators, and the executed workflow itself) sees
what was done before. The plain ``goal`` property is left untouched so run
records and the activity list stay readable and follow-up chains don't nest.
"""

import json
from typing import Any

PREVIOUS_RUN_CONTEXT_KEY = "previous_run_context"
MAX_PREVIOUS_GOAL_CHARS = 1000
MAX_PREVIOUS_OUTPUT_CHARS = 2000


def build_previous_run_context(run: Any) -> dict[str, Any]:
    """Build the JSON-serializable context dict for a previous run.

    Args:
        run: A completed WorkflowRun (duck-typed: id, goal, workflow_name,
            output, success).

    Returns:
        Dict suitable for the ``previous_run_context`` process property.
    """
    output = run.output
    if output is not None and not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False, default=str)
    return {
        "run_id": run.id,
        "goal": (run.goal or "")[:MAX_PREVIOUS_GOAL_CHARS],
        "workflow_name": run.workflow_name,
        "success": bool(run.success),
        "output": (output or "")[:MAX_PREVIOUS_OUTPUT_CHARS],
    }


def previous_run_id(properties: dict[str, Any]) -> str | None:
    """Return the ID of the run this process extends, if any."""
    ctx = properties.get(PREVIOUS_RUN_CONTEXT_KEY)
    if isinstance(ctx, dict):
        return ctx.get("run_id") or None
    return None


def with_previous_run(goal: str, properties: dict[str, Any]) -> str:
    """Return the goal, annotated with the previous run's context when present.

    Args:
        goal: The user's new goal.
        properties: Process properties (checked for ``previous_run_context``).

    Returns:
        The goal unchanged when there is no previous run; otherwise the goal
        followed by a delimited summary of the previous run.
    """
    ctx = properties.get(PREVIOUS_RUN_CONTEXT_KEY)
    if not isinstance(ctx, dict):
        return goal
    outcome = "succeeded" if ctx.get("success", True) else "failed"
    return (
        f"{goal}\n\n"
        "This goal is a follow-up to a previous run. Build on what was already done.\n"
        "<previous_run>\n"
        f"Previous goal: {ctx.get('goal', '')}\n"
        f"Workflow used: {ctx.get('workflow_name', '')}\n"
        f"Outcome: {outcome}\n"
        f"Previous output:\n{ctx.get('output', '')}\n"
        "</previous_run>"
    )

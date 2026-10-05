"""Follow-up and continuation goal support (F116, F134).

A goal can extend a previous completed run. Entry points store a compact
summary of that run in the ``previous_run_context`` process property; agent
actions call :func:`with_previous_run` so every step that reasons about the
goal (ethics gate, selector, creators, and the executed workflow itself) sees
what was done before. The plain ``goal`` property is left untouched so run
records and the activity list stay readable and follow-up chains don't nest.
"""

import json
import logging
from typing import Any

PREVIOUS_RUN_CONTEXT_KEY = "previous_run_context"
# F134/F135 continuation properties, copied onto the WorkflowRun record.
CONTINUATION_COMMENT_KEY = "continuation_comment"
CONTINUATION_DECISION_KEY = "continuation_decision"
CONTINUATION_RATIONALE_KEY = "continuation_rationale"
CONTINUATION_KEYS = (
    CONTINUATION_COMMENT_KEY,
    CONTINUATION_DECISION_KEY,
    CONTINUATION_RATIONALE_KEY,
)
MAX_PREVIOUS_GOAL_CHARS = 1000
MAX_PREVIOUS_OUTPUT_CHARS = 2000
# F134: caps on the enriched context so long chains/workflows stay compact.
MAX_TASKS = 20
MAX_TASK_TEXT_CHARS = 300
MAX_CHAIN_LINKS = 5
MAX_CHAIN_GOAL_CHARS = 200
MAX_COMMENT_CHARS = 2000

logger = logging.getLogger(__name__)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _task_progress(task_executions: list[Any]) -> list[dict[str, Any]]:
    """Summarise task executions as compact, JSON-serializable progress rows."""
    rows = []
    for ex in sorted(task_executions, key=lambda e: e.execution_order)[:MAX_TASKS]:
        row = {"task": ex.task_name or ex.task_definition_id, "state": ex.state}
        if ex.error:
            row["error"] = _as_text(ex.error)[:MAX_TASK_TEXT_CHARS]
        elif ex.output is not None:
            row["output"] = _as_text(ex.output)[:MAX_TASK_TEXT_CHARS]
        rows.append(row)
    return rows


def _chain_summary(chain: list[Any]) -> list[dict[str, Any]]:
    """Summarise earlier runs in a continuation chain (oldest first, capped)."""
    return [
        {
            "run_id": r.id,
            "goal": (r.goal or "")[:MAX_CHAIN_GOAL_CHARS],
            "workflow_name": r.workflow_name,
            "success": bool(r.success),
            "comment": (getattr(r, "continuation_comment", None) or "")[:MAX_TASK_TEXT_CHARS],
        }
        for r in chain[-MAX_CHAIN_LINKS:]
    ]


def build_previous_run_context(
    run: Any,
    task_executions: list[Any] | None = None,
    chain: list[Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON-serializable context dict for a previous run.

    Args:
        run: A finished WorkflowRun (duck-typed: id, goal, workflow_name,
            output, success, continuation_comment).
        task_executions: Optional task executions of *run* (F134) — summarised
            as task-level progress so a continuation knows where it got to.
        chain: Optional earlier runs in the continuation chain, oldest first,
            excluding *run* itself (F134). Summarised, never nested.

    Returns:
        Dict suitable for the ``previous_run_context`` process property.
    """
    ctx: dict[str, Any] = {
        "run_id": run.id,
        "goal": (run.goal or "")[:MAX_PREVIOUS_GOAL_CHARS],
        "workflow_name": run.workflow_name,
        "success": bool(run.success),
        "output": _as_text(run.output)[:MAX_PREVIOUS_OUTPUT_CHARS],
    }
    if getattr(run, "error", None):
        ctx["error"] = _as_text(run.error)[:MAX_TASK_TEXT_CHARS]
    if getattr(run, "continuation_comment", None):
        ctx["comment"] = run.continuation_comment[:MAX_TASK_TEXT_CHARS]
    if task_executions:
        ctx["tasks"] = _task_progress(task_executions)
    if chain:
        ctx["chain"] = _chain_summary(chain)
    return ctx


async def load_previous_run_context(metrics_store: Any, run_id: str | None) -> dict | None:
    """Load a finished run and build its enriched ``previous_run_context`` (F134).

    Works for successful and failed runs alike — anything with a metrics
    record and ``completed_at`` set. Task progress and chain summary are
    best-effort: store errors degrade to the F116 basic context.

    Args:
        metrics_store: A MetricsStore (scoped to the current user by the caller).
        run_id: The run to continue / follow up on.

    Returns:
        The context dict, or None if the run is unknown or still in progress.
    """
    run_id = (run_id or "").strip()
    if not run_id or metrics_store is None:
        return None
    run = await metrics_store.get_run(run_id)
    if run is None or run.completed_at is None:
        return None
    task_executions: list[Any] = []
    chain: list[Any] = []
    try:
        task_executions = await metrics_store.get_task_executions(run_id)
    except Exception:
        logger.warning("Could not load task executions for run %s", run_id, exc_info=True)
    try:
        chain = (await metrics_store.get_run_chain(run_id))[:-1]
    except Exception:
        logger.warning("Could not load continuation chain for run %s", run_id, exc_info=True)
    return build_previous_run_context(run, task_executions, chain)


def previous_run_id(properties: dict[str, Any]) -> str | None:
    """Return the ID of the run this process extends, if any."""
    ctx = properties.get(PREVIOUS_RUN_CONTEXT_KEY)
    if isinstance(ctx, dict):
        return ctx.get("run_id") or None
    return None


def continuation_fields(properties: dict[str, Any]) -> dict[str, str | None]:
    """Return the continuation fields to store on a WorkflowRun (F134/F135).

    Args:
        properties: Process properties.

    Returns:
        Dict keyed by WorkflowRun field name; values are None when unset.
    """
    return {key: (properties.get(key) or None) for key in CONTINUATION_KEYS}


def with_previous_run(goal: str, properties: dict[str, Any]) -> str:
    """Return the goal, annotated with the previous run's context when present.

    For a continuation (F134) the user's ``continuation_comment`` — where the
    previous run got to and what to do next — leads the annotation, followed
    by task-level progress and a compact summary of earlier runs in the chain.

    Args:
        goal: The user's new goal.
        properties: Process properties (checked for ``previous_run_context``
            and ``continuation_comment``).

    Returns:
        The goal unchanged when there is no previous run; otherwise the goal
        followed by a delimited summary of the previous run.
    """
    ctx = properties.get(PREVIOUS_RUN_CONTEXT_KEY)
    if not isinstance(ctx, dict):
        return goal
    comment = (properties.get(CONTINUATION_COMMENT_KEY) or "")[:MAX_COMMENT_CHARS]
    outcome = "succeeded" if ctx.get("success", True) else "failed"
    lines = [goal, ""]
    if comment:
        lines += [
            "This goal continues a previous run. Pick up where it got to, guided by "
            "the user's comment.",
            f"<continuation_comment>\n{comment}\n</continuation_comment>",
        ]
    else:
        lines.append("This goal is a follow-up to a previous run. Build on what was already done.")
    lines += [
        "<previous_run>",
        f"Previous goal: {ctx.get('goal', '')}",
        f"Workflow used: {ctx.get('workflow_name', '')}",
        f"Outcome: {outcome}",
    ]
    if ctx.get("error"):
        lines.append(f"Error: {ctx['error']}")
    tasks = ctx.get("tasks") or []
    if tasks:
        lines.append("Task progress:")
        for t in tasks:
            detail = t.get("error") or t.get("output") or ""
            lines.append(
                f"- {t.get('task', '')} [{t.get('state', '')}]" + (f": {detail}" if detail else "")
            )
    lines.append(f"Previous output:\n{ctx.get('output', '')}")
    lines.append("</previous_run>")
    chain = ctx.get("chain") or []
    if chain:
        lines.append("<earlier_runs>")
        for r in chain:
            status = "succeeded" if r.get("success") else "failed"
            note = f" — user comment: {r['comment']}" if r.get("comment") else ""
            lines.append(f"- {r.get('workflow_name', '')} ({status}): {r.get('goal', '')}{note}")
        lines.append("</earlier_runs>")
    return "\n".join(lines)

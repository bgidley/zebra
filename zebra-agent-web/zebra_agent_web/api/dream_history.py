"""Recent Dream Cycle runs, summarised for the /dreams/ page.

A dream cycle is a "Dream Cycle" process instance — started by the
``dream_cycle`` routine or ``POST /api/dream-cycle/``. Each step writes its
report to a process property (``metrics_analysis``, ``curation``,
``evaluation``, ``optimization_results``, ``dream_summary``); this module
flattens those into one dict per cycle for the template.
"""

from __future__ import annotations

import json
from typing import Any

from zebra_agent_web.api.models import (
    ProcessDefinitionModel,
    ProcessInstanceModel,
    RoutineRunModel,
)

DREAM_CYCLE_WORKFLOW = "Dream Cycle"
DREAM_CYCLE_ROUTINE = "dream_cycle"


def recent_dream_cycles(limit: int = 20) -> list[dict[str, Any]]:
    """Return the newest *limit* dream cycles, newest first (sync ORM).

    Not user-scoped: dream cycles are system processes, and scheduled ones
    carry no user.
    """
    definition_ids = ProcessDefinitionModel.objects.filter(name=DREAM_CYCLE_WORKFLOW).values_list(
        "id", flat=True
    )
    models = ProcessInstanceModel.objects.filter(
        definition_id__in=list(definition_ids), parent_process_id__isnull=True
    ).order_by("-created_at")[:limit]
    return [summarize_cycle(m) for m in models]


def next_scheduled_run():
    """Return the ``dream_cycle`` routine's run state, or None if never scheduled."""
    return RoutineRunModel.objects.filter(routine_name=DREAM_CYCLE_ROUTINE).first()


def summarize_cycle(model: ProcessInstanceModel) -> dict[str, Any]:
    """Flatten one Dream Cycle process into the fields the page shows."""
    props = json.loads(model.properties) if model.properties else {}
    metrics = _dict(props.get("metrics_analysis"))
    evaluation = _dict(props.get("evaluation"))
    assessment = _dict(evaluation.get("overall_assessment"))
    optimization = _dict(props.get("optimization_results"))
    curation = _dict(props.get("curation"))
    continuations = _dict(metrics.get("continuation_analysis"))

    duration = None
    if model.completed_at and model.created_at:
        duration = int((model.completed_at - model.created_at).total_seconds())

    retired = _list(curation.get("retired"))
    return {
        "id": model.id,
        "state": model.state,
        "started_at": model.created_at,
        "completed_at": model.completed_at,
        "duration": _format_duration(duration),
        "error": props.get("__error__"),
        "failed_task": props.get("__failed_task__"),
        "summary": _text(props.get("dream_summary")),
        "health_score": _score(assessment.get("health_score")),
        "health_summary": assessment.get("summary"),
        "key_issues": _list(assessment.get("key_issues")),
        "period_days": metrics.get("analysis_period_days"),
        "runs_analyzed": metrics.get("total_runs_analyzed"),
        "unique_workflows": metrics.get("unique_workflows"),
        "low_performers": _names(metrics.get("low_performers")),
        "high_performers": _names(metrics.get("high_performers")),
        "changes_made": _list(optimization.get("changes_made")),
        "failed_changes": _list(optimization.get("failed_changes")),
        "optimizer_dry_run": bool(optimization.get("dry_run")),
        "retired": retired,
        "retired_applied": sum(1 for r in retired if isinstance(r, dict) and r.get("applied")),
        "deferred_count": len(_list(curation.get("deferred"))),
        "curation_dry_run": bool(curation.get("dry_run")),
        "continuations": continuations.get("total_continuations", 0),
        "top_continued": _list(continuations.get("top_continued")),
        "capability_gaps": len(_list(continuations.get("capability_gaps"))),
    }


def _score(value: Any) -> int | None:
    """The evaluator's 0-100 health score; LLM output, so may be a string."""
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs}s" if minutes else f"{secs}s"


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _names(performers: Any) -> list[str]:
    """Workflow names from the analyzer's low/high performer lists."""
    return [
        p.get("workflow_name", "") if isinstance(p, dict) else str(p) for p in _list(performers)
    ]


def _text(value: Any) -> str:
    """``dream_summary`` is the llm_call output: a string, or a dict holding one."""
    if isinstance(value, dict):
        value = value.get("content") or value.get("response") or ""
    return value if isinstance(value, str) else ""

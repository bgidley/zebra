"""Read model for the ``/gym/`` page (#171).

Turns golden tasks and stored ``GymScore`` records into what the page shows:
each golden task with its latest score for the current version and its recent
scores, and the recent gate decisions on self-modified workflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebra_agent.gym import GoldenTask
    from zebra_agent.metrics import GymScore

#: Recent scores shown per golden task.
HISTORY_LENGTH = 10
#: Gate decisions shown.
DECISION_LIMIT = 10


def _mean(scores: list[float | None]) -> float | None:
    values = [s for s in scores if s is not None]
    if not values or len(values) != len(scores):
        return None
    return round(sum(values) / len(values), 2)


def golden_task_rows(golden: list[GoldenTask], scores: list[GymScore]) -> list[dict[str, Any]]:
    """One row per golden task: latest current-version score and recent history.

    *scores* are newest first. History is oldest first, so it reads left to right.
    """
    rows = []
    for task in golden:
        mine = [s for s in scores if s.golden_id == task.id and s.variant == "current"]
        recent = mine[:HISTORY_LENGTH]
        latest = recent[0] if recent else None
        rows.append(
            {
                "task": task,
                "latest": latest,
                "history": list(reversed(recent)),
            }
        )
    return rows


def gate_decisions(scores: list[GymScore]) -> list[dict[str, Any]]:
    """Gate decisions, newest first: one per (gym run, workflow) with a candidate scored."""
    groups: dict[tuple[str, str], list[GymScore]] = {}
    for score in scores:
        if (score.details or {}).get("mode") != "gate":
            continue
        groups.setdefault((score.gym_run_id, score.workflow_name), []).append(score)

    decisions = []
    for (gym_run_id, workflow_name), group in groups.items():
        candidates = [s for s in group if s.variant == "candidate"]
        if not candidates:
            continue
        current = [s for s in group if s.variant == "current"]
        decisions.append(
            {
                "gym_run_id": gym_run_id,
                "workflow_name": workflow_name,
                "decision": (candidates[0].details or {}).get("decision", ""),
                "current_mean": _mean([s.score for s in current]),
                "candidate_mean": _mean([s.score for s in candidates]),
                "golden_ids": sorted({s.golden_id for s in group}),
                "at": max(s.created_at for s in group),
            }
        )
    decisions.sort(key=lambda d: d["at"], reverse=True)
    return decisions[:DECISION_LIMIT]

"""Continuation-chain analysis for the dream cycle (F136).

A continued goal is a learning signal: the original workflow did not fully
satisfy the user. This module gathers continuation chains from a MetricsStore
(``get_continuations_since`` + ``get_run_chain`` + ``get_task_executions``)
and turns them into findings and targeted improvement proposals that the
workflow evaluator / optimizer can act on.

All functions are deterministic (no LLM) and tolerate the lineage fields
``continuation_comment`` / ``continuation_decision`` / ``continuation_rationale``
being ``None``.
"""

import logging
from collections import Counter
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

NEW_WORKFLOW = "new_workflow"
TOP_N = 5


def empty_continuation_analysis() -> dict[str, Any]:
    """Return the continuation block used when there is nothing to analyse."""
    return {
        "total_continuations": 0,
        "total_chains": 0,
        "chains": [],
        "frequently_continued": [],
        "top_continued": [],
        "capability_gaps": [],
        "added_steps": [],
        "decision_counts": {},
        "proposals": [],
        "continued_run_ids": [],
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _task_summary(executions: list) -> dict[str, Any]:
    """Describe where a run got to from its task executions."""
    tasks = [
        {
            "task_definition_id": e.task_definition_id,
            "task_name": e.task_name,
            "state": e.state,
        }
        for e in executions
    ]
    last = tasks[-1] if tasks else None
    return {
        "tasks": tasks,
        "last_task": last["task_name"] if last else None,
        "last_state": last["state"] if last else None,
        "incomplete_tasks": [t["task_name"] for t in tasks if t["state"] != "complete"],
    }


async def _executions(metrics_store: Any, run_id: str, cache: dict[str, list]) -> list:
    if run_id not in cache:
        try:
            cache[run_id] = list(await metrics_store.get_task_executions(run_id))
        except Exception as e:  # task history is optional detail
            logger.warning("Could not load task executions for run %s: %s", run_id, e)
            cache[run_id] = []
    return cache[run_id]


async def analyze_continuations(
    metrics_store: Any,
    cutoff: datetime,
    min_continuations_for_proposal: int = 2,
) -> dict[str, Any]:
    """Gather and analyse continuation chains whose continuations started since *cutoff*.

    Args:
        metrics_store: A MetricsStore (needs get_continuations_since, get_run_chain,
            get_task_executions).
        cutoff: Start of the analysis window.
        min_continuations_for_proposal: How often a workflow must be continued before
            an "extend this workflow" proposal is made.

    Returns:
        The ``continuation_analysis`` dict (see ``empty_continuation_analysis``).
    """
    continuations = list(await metrics_store.get_continuations_since(cutoff))
    if not continuations:
        logger.info("Dream cycle: no continuations since %s", cutoff.isoformat())
        return empty_continuation_analysis()

    # Leaves: continuations nobody continued further. Each yields one chain.
    predecessor_ids = {r.extends_run_id for r in continuations}
    leaves = [r for r in continuations if r.id not in predecessor_ids]
    if not leaves:  # pathological cycle — fall back to every continuation
        leaves = continuations

    exec_cache: dict[str, list] = {}
    chains: list[dict[str, Any]] = []
    # link key = continuation run id -> (predecessor run, continuation run)
    links: dict[str, tuple[Any, Any]] = {}

    for leaf in leaves:
        chain_runs = list(await metrics_store.get_run_chain(leaf.id))
        if len(chain_runs) < 2:
            continue
        root = chain_runs[0]
        root_execs = await _executions(metrics_store, root.id, exec_cache)
        steps = []
        for prev, cont in zip(chain_runs, chain_runs[1:], strict=False):
            links[cont.id] = (prev, cont)
            cont_execs = await _executions(metrics_store, cont.id, exec_cache)
            steps.append(
                {
                    "run_id": cont.id,
                    "workflow_name": cont.workflow_name,
                    "comment": cont.continuation_comment,
                    "decision": cont.continuation_decision,
                    "rationale": cont.continuation_rationale,
                    "success": bool(cont.success),
                    "tasks": [e.task_name for e in cont_execs],
                }
            )
        final = chain_runs[-1]
        chains.append(
            {
                "root_run_id": root.id,
                "leaf_run_id": final.id,
                "length": len(chain_runs),
                "original_workflow": root.workflow_name,
                "original_goal": (root.goal or "")[:200],
                "original_success": bool(root.success),
                "original_started_at": _iso(root.started_at),
                "stopped_at": _task_summary(root_execs),
                "continuations": steps,
                "final_outcome": {
                    "workflow_name": final.workflow_name,
                    "success": bool(final.success),
                    "error": final.error,
                },
            }
        )

    # Patterns over unique links (continuation -> its predecessor).
    by_workflow: dict[str, list[tuple[Any, Any]]] = {}
    for prev, cont in links.values():
        by_workflow.setdefault(prev.workflow_name, []).append((prev, cont))

    decision_counts: Counter[str] = Counter(
        (cont.continuation_decision or "unknown") for _, cont in links.values()
    )

    # Steps users added after the fact: completed tasks run by a different
    # workflow in the continuation that the predecessor did not run.
    added: dict[str, Counter[str]] = {}
    for prev, cont in links.values():
        if cont.workflow_name == prev.workflow_name:
            continue
        prev_ids = {
            e.task_definition_id for e in await _executions(metrics_store, prev.id, exec_cache)
        }
        for e in await _executions(metrics_store, cont.id, exec_cache):
            if e.state == "complete" and e.task_definition_id not in prev_ids:
                added.setdefault(prev.workflow_name, Counter())[e.task_name] += 1

    added_steps = [
        {"workflow_name": wf, "step": step, "count": count}
        for wf, counter in added.items()
        for step, count in counter.most_common()
    ]
    added_steps.sort(key=lambda s: s["count"], reverse=True)

    frequently_continued = []
    for wf, pairs in by_workflow.items():
        comments = [c.continuation_comment for _, c in pairs if c.continuation_comment]
        frequently_continued.append(
            {
                "workflow_name": wf,
                "continuation_count": len(pairs),
                "comments": comments[:TOP_N],
                "decisions": dict(
                    Counter((c.continuation_decision or "unknown") for _, c in pairs)
                ),
                "continued_into": dict(Counter(c.workflow_name for _, c in pairs)),
                "added_steps": [s["step"] for s in added_steps if s["workflow_name"] == wf][:TOP_N],
            }
        )
    frequently_continued.sort(key=lambda f: f["continuation_count"], reverse=True)

    capability_gaps = [
        {
            "original_workflow": prev.workflow_name,
            "continuation_workflow": cont.workflow_name,
            "continuation_run_id": cont.id,
            "comment": cont.continuation_comment,
            "rationale": cont.continuation_rationale,
            "success": bool(cont.success),
        }
        for prev, cont in links.values()
        if cont.continuation_decision == NEW_WORKFLOW
    ]

    proposals = _build_proposals(
        frequently_continued, capability_gaps, min_continuations_for_proposal
    )

    return {
        "total_continuations": len(links),
        "total_chains": len(chains),
        "chains": chains,
        "frequently_continued": frequently_continued,
        "top_continued": [
            {"workflow_name": f["workflow_name"], "count": f["continuation_count"]}
            for f in frequently_continued[:TOP_N]
        ],
        "capability_gaps": capability_gaps,
        "added_steps": added_steps,
        "decision_counts": dict(decision_counts),
        "proposals": proposals,
        "continued_run_ids": sorted({prev.id for prev, _ in links.values()}),
    }


def _build_proposals(
    frequently_continued: list[dict[str, Any]],
    capability_gaps: list[dict[str, Any]],
    min_continuations: int,
) -> list[dict[str, Any]]:
    """Turn continuation findings into evaluator-style improvement priorities.

    ``kind`` is ``extend`` (grow a frequently continued workflow) or ``promote``
    (make a continuation-created workflow a reusable library workflow). Promote
    proposals start as ``enhance``; the evaluator switches them to ``create`` when
    the workflow is not in the library.
    """
    proposals: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for fc in frequently_continued:
        if fc["continuation_count"] < min_continuations:
            continue
        wf = fc["workflow_name"]
        parts = [f"Extend '{wf}' so users no longer need to continue it."]
        if fc["comments"]:
            parts.append("Users asked: " + "; ".join(f'"{c}"' for c in fc["comments"]) + ".")
        if fc["added_steps"]:
            parts.append(
                "Add the steps continuations had to run afterwards: "
                + ", ".join(fc["added_steps"])
                + "."
            )
        proposals.append(
            {
                "type": "enhance",
                "kind": "extend",
                "target": wf,
                "action": " ".join(parts),
                "expected_impact": "high" if fc["continuation_count"] >= 3 else "medium",
                "rationale": (
                    f"'{wf}' was continued {fc['continuation_count']} times in the analysis "
                    "window — its output did not fully satisfy users."
                ),
                "source": "continuation",
            }
        )
        seen.add(("enhance", wf))

    for gap in capability_gaps:
        target = gap["continuation_workflow"]
        if not gap["success"]:
            continue
        if ("enhance", target) in seen:
            continue
        seen.add(("enhance", target))
        why = gap["comment"] or gap["rationale"] or "a capability the library lacked"
        proposals.append(
            {
                "type": "enhance",
                "kind": "promote",
                "target": target,
                "action": (
                    f"Promote '{target}' (created for a continuation of "
                    f"'{gap['original_workflow']}') into a reusable library workflow: "
                    f"generalise its description and use_when to cover goals like: {why}."
                ),
                "expected_impact": "medium",
                "rationale": (
                    "A continuation needed a new workflow — a missing capability "
                    f"after '{gap['original_workflow']}'."
                ),
                "source": "continuation",
            }
        )

    for i, p in enumerate(proposals, start=1):
        p["priority"] = i
    return proposals

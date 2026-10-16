"""CompareOutcomeReviewsAction - reconcile two reviews of a change against its outcomes (#190).

The *Outcome Review* workflow has Zebra review a shipped change blind, then
compares its verdicts with Claude's. Each review is
``{"verdicts": [{"id": "O1", "verdict": "met|partial|missed", "evidence": "..."}]}``
(a bare list, or JSON text in a code fence, also works). Outcomes on which the
two disagree, or which either side left out or garbled, are disputed: a review
that cannot be read never counts as agreement.
"""

import json
import logging
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

VERDICTS = ("met", "partial", "missed")


def parse_review(value: Any) -> dict[str, dict[str, str]]:
    """Return ``{outcome_id: {"verdict", "evidence"}}`` from a review, or {} if unreadable.

    A verdict that is not met / partial / missed is kept as ``""`` so the outcome
    still shows up (and is disputed) rather than vanishing.
    """
    if isinstance(value, str):
        text = value.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        try:
            value = json.loads(text)
        except ValueError:
            return {}
    if isinstance(value, dict):
        value = value.get("verdicts", [])
    if not isinstance(value, list):
        return {}

    parsed: dict[str, dict[str, str]] = {}
    for item in value:
        if not isinstance(item, dict) or not str(item.get("id", "")).strip():
            continue
        verdict = str(item.get("verdict", "")).strip().lower()
        parsed[str(item["id"]).strip().upper()] = {
            "verdict": verdict if verdict in VERDICTS else "",
            "evidence": str(item.get("evidence", "")).strip(),
        }
    return parsed


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|") or "—"


def _sort_key(outcome_id: str) -> tuple[int, str]:
    digits = re.sub(r"\D", "", outcome_id)
    return (int(digits) if digits else 10**6, outcome_id)


def compare_reviews(
    zebra: dict[str, dict[str, str]], claude: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Line up two parsed reviews per outcome."""
    rows = []
    for oid in sorted(set(zebra) | set(claude), key=_sort_key):
        z = zebra.get(oid, {"verdict": "", "evidence": ""})
        c = claude.get(oid, {"verdict": "", "evidence": ""})
        rows.append(
            {
                "id": oid,
                "zebra": z["verdict"],
                "claude": c["verdict"],
                "zebra_evidence": z["evidence"],
                "claude_evidence": c["evidence"],
                "agreed": bool(z["verdict"]) and z["verdict"] == c["verdict"],
            }
        )
    disputed = [r["id"] for r in rows if not r["agreed"]]
    if not rows:
        disputed = ["(no verdicts)"]
    return {
        "status": "disputed" if disputed else "agreed",
        "rows": rows,
        "disputed": disputed,
        "followups": [r["id"] for r in rows if r["agreed"] and r["zebra"] != "met"],
        "table_markdown": _table(rows),
        "dispute_notes": _dispute_notes(rows),
    }


def _table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| # | Zebra | Claude | Agreed | Zebra's evidence | Claude's evidence |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['zebra'] or '?'} | {r['claude'] or '?'} | "
            f"{'yes' if r['agreed'] else '**no**'} | {_cell(r['zebra_evidence'])} | "
            f"{_cell(r['claude_evidence'])} |"
        )
    if not rows:
        lines.append("| — | ? | ? | **no** | No readable verdicts | No readable verdicts |")
    return "\n".join(lines)


def _dispute_notes(rows: list[dict[str, Any]]) -> str:
    notes = []
    for r in rows:
        if r["agreed"]:
            continue
        notes.append(
            f"{r['id']}: Zebra said {r['zebra'] or 'nothing readable'} "
            f"({r['zebra_evidence'] or 'no evidence'}); Claude said "
            f"{r['claude'] or 'nothing readable'} ({r['claude_evidence'] or 'no evidence'})."
        )
    return "\n".join(notes) or "No readable verdicts from either reviewer."


class CompareOutcomeReviewsAction(TaskAction):
    """Compare Zebra's and Claude's per-outcome verdicts and route on agreement.

    Example workflow usage:
        ```yaml
        compare:
          action: compare_outcome_reviews
          properties:
            zebra_key: zebra_review
            claude_key: claude_review
            output_key: review_result
        ```

    With ``reconsidered_key`` the verdicts there replace Zebra's first ones for the
    outcomes they cover. With ``ruling_key`` (a human task id) the result records the
    human's ruling, status ``ruled``, and no route is set. ``final: true`` also sets no
    route, for the workflow's last step.
    """

    description = (
        "Compare two per-outcome reviews (Zebra's and Claude's); route 'agreed' when every "
        "verdict matches, 'disputed' otherwise, or record a human ruling."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="zebra_key",
            type="string",
            description="Process property holding Zebra's review",
            required=False,
            default="zebra_review",
        ),
        ParameterDef(
            name="claude_key",
            type="string",
            description="Process property holding Claude's review",
            required=False,
            default="claude_review",
        ),
        ParameterDef(
            name="reconsidered_key",
            type="string",
            description="Process property holding Zebra's reconsidered verdicts",
            required=False,
        ),
        ParameterDef(
            name="ruling_key",
            type="string",
            description="Human task id whose output is the ruling on disputed outcomes",
            required=False,
        ),
        ParameterDef(
            name="final",
            type="bool",
            description="Record the result without routing (last step)",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the comparison",
            required=False,
            default="review_result",
        ),
    ]
    outputs = [
        ParameterDef(name="status", type="string", description="agreed, disputed or ruled"),
        ParameterDef(name="rows", type="list", description="Per-outcome verdicts"),
        ParameterDef(name="disputed", type="list", description="Disputed outcome ids"),
        ParameterDef(
            name="followups", type="list", description="Outcomes agreed as partial or missed"
        ),
        ParameterDef(name="table_markdown", type="string", description="Side-by-side table"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Compare the reviews and store the result under ``output_key``."""
        props = task.properties
        zebra = parse_review(context.get_process_property(props.get("zebra_key", "zebra_review")))
        if props.get("reconsidered_key"):
            zebra.update(parse_review(context.get_process_property(props["reconsidered_key"])))
        claude = parse_review(
            context.get_process_property(props.get("claude_key", "claude_review"))
        )

        result = compare_reviews(zebra, claude)
        output_key = props.get("output_key", "review_result")

        ruling_key = props.get("ruling_key")
        if ruling_key:
            ruling = context.get_process_property(f"__task_output_{ruling_key}") or {}
            result["status"] = "ruled"
            result["ruling"] = ruling.get("ruling", "") if isinstance(ruling, dict) else ruling
        if ruling_key or props.get("final"):
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        logger.info(
            "Outcome review %s: %d outcomes, disputed %s",
            result["status"],
            len(result["rows"]),
            result["disputed"],
        )
        context.set_process_property(output_key, result)
        return TaskResult(success=True, output=result, next_route=result["status"])

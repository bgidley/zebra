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


def outcome_texts(outcomes: Any) -> dict[str, str]:
    """``{id: outcome}`` from the first two cells of a markdown outcomes table (#215)."""
    texts = {}
    for line in str(outcomes or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and re.fullmatch(r"[A-Za-z]+\d+", cells[0] or ""):
            texts[cells[0].upper()] = cells[1] if len(cells) > 1 else ""
    return texts


def outcome_ids(outcomes: Any) -> set[str]:
    """Outcome ids from the first cell of a markdown outcomes table (header and rules skipped)."""
    return set(outcome_texts(outcomes))


def compare_reviews(
    zebra: dict[str, dict[str, str]],
    claude: dict[str, dict[str, str]],
    expected: set[str] | None = None,
    texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Line up two parsed reviews per outcome.

    ``expected`` ids (from the outcomes table) are always compared, so an outcome
    that neither reviewer judged is disputed rather than silently skipped.
    ``texts`` (from ``outcome_texts``) name each outcome in the summary and notes.
    """
    rows = []
    for oid in sorted(set(zebra) | set(claude) | (expected or set()), key=_sort_key):
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
        "summary_markdown": _summary(rows, texts or {}),
        "dispute_notes": _dispute_notes(rows, texts or {}),
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


def _summary(rows: list[dict[str, Any]], texts: dict[str, str]) -> str:
    """Verdicts without evidence, narrow enough for the ruling form (#215)."""
    lines = ["| # | Outcome | Zebra | Claude | Agreed |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['id']} | {_cell(texts.get(r['id'], ''))} | {r['zebra'] or '?'} | "
            f"{r['claude'] or '?'} | {'yes' if r['agreed'] else '**no**'} |"
        )
    if not rows:
        lines.append("| — | No readable verdicts | ? | ? | **no** |")
    return "\n".join(lines)


def _dispute_notes(rows: list[dict[str, Any]], texts: dict[str, str]) -> str:
    """One markdown section per disputed outcome: both verdicts, the outcome, each side's case."""
    notes = []
    for r in rows:
        if r["agreed"]:
            continue
        section = [
            f"#### {r['id']}: Zebra {r['zebra'] or 'nothing readable'}, "
            f"Claude {r['claude'] or 'nothing readable'}"
        ]
        if texts.get(r["id"]):
            section.append(f"*{texts[r['id']]}*")
        section.append(f"**Zebra:** {r['zebra_evidence'] or 'no evidence'}")
        section.append(f"**Claude:** {r['claude_evidence'] or 'no evidence'}")
        notes.append("\n\n".join(section))
    return "\n\n".join(notes) or "No readable verdicts from either reviewer."


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
            name="outcomes_key",
            type="string",
            description="Process property holding the outcomes table; every id in it is compared",
            required=False,
            default="outcomes",
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
        ParameterDef(
            name="summary_markdown",
            type="string",
            description="Verdicts per outcome without evidence (for the ruling form)",
        ),
        ParameterDef(
            name="dispute_notes",
            type="string",
            description="Markdown section per disputed outcome with both sides' evidence",
        ),
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

        texts = outcome_texts(context.get_process_property(props.get("outcomes_key", "outcomes")))
        result = compare_reviews(zebra, claude, set(texts), texts)
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

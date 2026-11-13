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

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import complete_json

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


def _inert(text: str) -> str:
    """Text safe inside a generated form: the form resolves ``{{templates}}`` in defaults."""
    return str(text).replace("{{", "{ {").replace("}}", "} }")


def first_sentence(text: str, limit: int = 240) -> str:
    """The first sentence of a reviewer's evidence, capped: the brief's fallback position (#295)."""
    flat = " ".join(str(text or "").split())
    match = re.match(r"(.+?\.)(\s|$)", flat)
    sentence = match.group(1) if match else flat
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def field_key(outcome_id: str) -> str:
    """Form field name for an outcome's verdict (``O1``); ``_note`` / ``_case`` are added to it."""
    return re.sub(r"\W", "_", outcome_id)


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
    change: str = "",
) -> dict[str, Any]:
    """Line up two parsed reviews per outcome.

    ``expected`` ids (from the outcomes table) are always compared, so an outcome
    that neither reviewer judged is disputed rather than silently skipped.
    ``texts`` (from ``outcome_texts``) name each outcome in the summary and notes;
    ``change`` (issue, title, commit) heads the ruling form.
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
        "ruling_form": ruling_form(rows, texts or {}, None, change),
    }


def _table(rows: list[dict[str, Any]]) -> str:
    """The issue table; a Ruling column appears once a human has ruled (#295)."""
    ruled = any(r.get("ruling") for r in rows)
    head = "| # | Zebra | Claude | Agreed |" + (" Ruling |" if ruled else "")
    lines = [
        head + " Zebra's evidence | Claude's evidence |",
        "|---|---|---|---|---|---|" + ("---|" if ruled else ""),
    ]
    for r in rows:
        ruling = ""
        if ruled:
            note = f" ({_cell(r['ruling_note'])})" if r.get("ruling_note") else ""
            ruling = f" **{r['ruling']}**{note} |" if r.get("ruling") else " — |"
        lines.append(
            f"| {r['id']} | {r['zebra'] or '?'} | {r['claude'] or '?'} | "
            f"{'yes' if r['agreed'] else '**no**'} |{ruling} {_cell(r['zebra_evidence'])} | "
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


def change_line(context: ExecutionContext) -> str:
    """``#295 Title (abc1234)`` from the process's ``issue``, ``title`` and ``deployed_hash``."""
    issue, title, commit = (
        str(context.get_process_property(k) or "").strip()
        for k in ("issue", "title", "deployed_hash")
    )
    line = " ".join(p for p in (f"#{issue}" if issue else "", title) if p)
    return f"{line} ({commit})" if commit and line else line or commit


def _verdict_labels(row: dict[str, Any]) -> list[str]:
    """Picker labels naming who said which, e.g. ``Partial (Zebra)`` / ``Met (Claude)``."""
    labels = []
    for verdict in VERDICTS:
        said = [who for who in ("zebra", "claude") if row[who] == verdict]
        names = " and ".join(w.capitalize() for w in said)
        labels.append(f"{verdict.capitalize()} ({names})" if names else verdict.capitalize())
    return labels


def _case(row: dict[str, Any], text: str, brief: dict[str, str]) -> str:
    """The read-only section above an outcome's picker: what it is, the crux, both positions."""
    lines = []
    if text:
        lines += [f"*{text}*", ""]
    if brief.get("crux"):
        lines += [
            f"**In dispute:** {brief['crux']}",
            "",
            "_Summary by a low-tier model, not a verdict; the full evidence is at the end._",
            "",
        ]
    lines += ["| | Verdict | Position |", "|---|---|---|"]
    for who in ("zebra", "claude"):
        position = brief.get(who) or first_sentence(row[f"{who}_evidence"]) or "no evidence"
        lines.append(f"| **{who.capitalize()}** | {row[who] or '?'} | {_cell(position)} |")
    if brief.get("settle"):
        lines += ["", f"**What would settle it:** {brief['settle']}"]
    return _inert("\n".join(lines))


def ruling_form(
    rows: list[dict[str, Any]],
    texts: dict[str, str],
    briefs: dict[str, dict[str, str]] | None = None,
    change: str = "",
) -> dict[str, Any]:
    """JSON Schema for the human ruling: one section and one required pick per disputed outcome.

    Per disputed outcome: ``<id>_case`` (read-only: outcome, crux, both verdicts and positions,
    what would settle it), ``<id>`` (met / partial / missed, labelled with who said which) and
    ``<id>_note``. Agreed outcomes are one line at the top; the full evidence is at the end
    (#295). ``briefs`` come from ``brief_outcome_disputes``; without one an outcome shows each
    side's first sentence.
    """
    briefs = briefs or {}
    disputed = [r for r in rows if not r["agreed"]]
    agreed = [r for r in rows if r["agreed"]]
    props: dict[str, Any] = {}
    required: list[str] = []
    if agreed:
        props["agreed"] = {
            "type": "string",
            "title": "Agreed",
            "readOnly": True,
            "default": " · ".join(f"{r['id']} {r['zebra']}" for r in agreed),
        }
    for r in disputed:
        key = field_key(r["id"])
        props[f"{key}_case"] = {
            "type": "string",
            "title": f"{r['id']}: Zebra {r['zebra'] or '?'}, Claude {r['claude'] or '?'}",
            "readOnly": True,
            "default": _case(r, texts.get(r["id"], ""), briefs.get(r["id"], {})),
        }
        props[key] = {
            "type": "string",
            "title": f"Your verdict on {r['id']}",
            "enum": list(VERDICTS),
            "enumLabels": _verdict_labels(r),
        }
        props[f"{key}_note"] = {
            "type": "string",
            "title": f"Note on {r['id']} (optional)",
            "description": "Why, or what to follow up. Partial and missed become follow-ups.",
        }
        required.append(key)
    if not disputed:
        # No readable verdicts at all: nothing to pick from, so ask in words.
        props["ruling"] = {
            "type": "string",
            "title": "Your ruling",
            "format": "multiline",
            "description": "Neither review could be read. Rule on each outcome in words.",
        }
        required.append("ruling")
    else:
        props["notes"] = {
            "type": "string",
            "title": "Anything else (optional)",
            "format": "multiline",
        }
    props["evidence"] = {
        "type": "string",
        "title": "Full evidence",
        "readOnly": True,
        "default": _inert(_dispute_notes(rows, texts)),
    }
    n = len(disputed)
    return {
        "type": "object",
        "title": f"Zebra and Claude disagree on {n} of {len(rows)} outcomes"
        if n
        else "Zebra and Claude's reviews could not be compared",
        "description": _inert(
            (f"{change}\n" if change else "")
            + "Pick a verdict for each disputed outcome. The delivering session stays blocked "
            "until you submit."
        ),
        "required": required,
        "properties": props,
    }


def record_ruling(result: dict[str, Any], answer: Any) -> dict[str, Any]:
    """Fold the human's answer into ``result``: per-outcome rulings, follow-ups, a summary.

    ``answer`` is the ruling form's output. A pick per disputed outcome sets that row's
    ``ruling`` (and ``ruling_note``); a ruled partial or missed outcome joins ``followups``.
    A v5 free-text answer (``{"ruling": "..."}``) or a bare string is kept as ``ruling``.
    """
    answer = answer if isinstance(answer, dict) else {"ruling": answer or ""}
    lines = []
    for r in result["rows"]:
        if r["agreed"]:
            continue
        key = field_key(r["id"])
        verdict = str(answer.get(key) or "").strip().lower()
        if verdict not in VERDICTS:
            continue
        note = " ".join(str(answer.get(f"{key}_note") or "").split())
        r["ruling"], r["ruling_note"] = verdict, note
        lines.append(f"{r['id']}: {verdict}" + (f": {note}" if note else ""))
        if verdict != "met" and r["id"] not in result["followups"]:
            result["followups"].append(r["id"])
    result["followups"].sort(key=_sort_key)
    extra = str(answer.get("notes") or answer.get("ruling") or "").strip()
    if extra:
        lines.append(extra)
    result["status"] = "ruled"
    result["ruling"] = "\n".join(lines)
    result["unruled"] = [
        r["id"] for r in result["rows"] if not r["agreed"] and not r.get("ruling")
    ] or (["(no verdicts)"] if not result["rows"] else [])
    result["table_markdown"] = _table(result["rows"])
    return result


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
        result = compare_reviews(zebra, claude, set(texts), texts, change_line(context))
        output_key = props.get("output_key", "review_result")
        previous = context.get_process_property(output_key)
        if isinstance(previous, dict) and previous.get("briefs"):
            result["briefs"] = previous["briefs"]

        ruling_key = props.get("ruling_key")
        if ruling_key:
            record_ruling(result, context.get_process_property(f"__task_output_{ruling_key}"))
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


BRIEF_SYSTEM_PROMPT = """\
Two reviewers, Zebra and Claude, judged a shipped code change against agreed outcomes and still
disagree on some of them. A human will rule. Your job is to make the disagreement easy to see,
NOT to decide it: never say who is right, never add your own verdict, never invent evidence.

For each disputed outcome, from the two reviewers' evidence only, write:
- crux: the one specific point they differ on, in one sentence (e.g. "Whether lock-file lines
  are scanned for personal data", not "They disagree about O1").
- zebra: Zebra's position on that point, one sentence, with its key file:line if it gave one.
- claude: Claude's position on that point, one sentence, with its key file:line if it gave one.
- settle: the one check a person could make to decide it (a file to read, a test to run, a
  prod page to look at), one sentence.
If a reviewer did not address the other's point, say so in its position.

Reply with JSON only:
{"disputes": [{"id": "O1", "crux": "...", "zebra": "...", "claude": "...", "settle": "..."}]}
"""

BRIEF_FIELDS = ("crux", "zebra", "claude", "settle")
MAX_BRIEF_CHARS = 400

# A brief that takes a side is dropped: the human rules, the summariser never does (#295).
TAKES_A_SIDE = re.compile(
    r"\b(?:zebra|claude|reviewer)(?:'s|\s+(?:is|was|are))\s+(?:right|correct|wrong|mistaken)\b"
    r"|\b(?:should|must|ought to)\s+(?:be|stay|remain)\s+(?:rated\s+)?(?:met|partial|missed)\b"
    r"|\b(?:correct|right|true)\s+verdict\b"
    r"|\b(?:i|we)\s+(?:recommend|suggest|would rule|side with|agree with)\b"
    r"|\brule\s+(?:in favou?r|for)\b",
    re.IGNORECASE,
)


def takes_a_side(text: str) -> bool:
    """True when brief text recommends a verdict or says which reviewer is right."""
    return bool(TAKES_A_SIDE.search(text))


def brief_prompt(rows: list[dict[str, Any]], texts: dict[str, str]) -> str:
    """Both reviewers' full cases for each disputed outcome, for the brief."""
    parts = []
    for r in rows:
        if r["agreed"]:
            continue
        parts.append(
            f"## {r['id']}: {texts.get(r['id'], '')}\n"
            f"Zebra's verdict: {r['zebra'] or 'none'}\n"
            f"Zebra's evidence: {r['zebra_evidence'] or 'none'}\n"
            f"Claude's verdict: {r['claude'] or 'none'}\n"
            f"Claude's evidence: {r['claude_evidence'] or 'none'}"
        )
    return "\n\n".join(parts)


def parse_briefs(value: Any, ids: set[str]) -> dict[str, dict[str, str]]:
    """``{id: {crux, zebra, claude, settle}}`` for the disputed ``ids`` the reply covers.

    Unknown ids, non-string fields and fields that take a side (``takes_a_side``) are
    dropped, then briefs left without a crux; text is capped.
    """
    items = value.get("disputes", []) if isinstance(value, dict) else value
    briefs: dict[str, dict[str, str]] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("id", "")).strip().upper()
        sided = [k for k in BRIEF_FIELDS if isinstance(item.get(k), str) and takes_a_side(item[k])]
        if sided:
            logger.info("Outcome dispute brief %s: dropped %s for taking a side", oid, sided)
        brief = {
            k: " ".join(item[k].split())[:MAX_BRIEF_CHARS]
            for k in BRIEF_FIELDS
            if isinstance(item.get(k), str) and item[k].strip() and not takes_a_side(item[k])
        }
        if oid in ids and brief.get("crux"):
            briefs[oid] = brief
    return briefs


class BriefOutcomeDisputesAction(TaskAction):
    """Boil each still-disputed outcome down to its crux for the human ruling form (#295).

    One low-tier LLM call reads both reviewers' evidence and returns, without judging, the
    point they differ on, each side's position in a sentence and what would settle it. The
    result goes into ``review_result.briefs`` and the ruling form is rebuilt with it. It never
    fails: with no LLM, an error or an unusable reply the form keeps each side's first sentence.

    Example workflow usage:
        ```yaml
        brief_disputes:
          action: brief_outcome_disputes
          properties:
            result_key: review_result
        ```
    """

    description = (
        "Summarise where two outcome reviews disagree (crux, each side's position, what would "
        "settle it) for the human ruling form; never judges, never fails."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="result_key",
            type="string",
            description="Process property holding the comparison (review_result)",
            required=False,
            default="review_result",
        ),
        ParameterDef(
            name="outcomes_key",
            type="string",
            description="Process property holding the outcomes table",
            required=False,
            default="outcomes",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="Model tier for the brief",
            required=False,
            default="low",
        ),
    ]
    outputs = [
        ParameterDef(name="briefed", type="list", description="Outcome ids with a brief"),
        ParameterDef(name="error", type="string", description="Why there is no brief, if none"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Brief the disputed outcomes and rebuild the ruling form; always succeeds."""
        props = task.properties
        result_key = props.get("result_key", "review_result")
        result = context.get_process_property(result_key)
        if not isinstance(result, dict) or not result.get("rows"):
            return TaskResult.ok(output={"briefed": [], "error": "nothing to brief"})
        texts = outcome_texts(context.get_process_property(props.get("outcomes_key", "outcomes")))
        ids = {r["id"] for r in result["rows"] if not r["agreed"]}

        briefs: dict[str, dict[str, str]] = {}
        error = ""
        try:
            llm = get_llm(model_for(task, context, default="low"), context)
            reply = await complete_json(
                llm,
                [
                    Message.system(BRIEF_SYSTEM_PROMPT),
                    Message.user(brief_prompt(result["rows"], texts)),
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            briefs = parse_briefs(reply, ids)
            if not briefs:
                error = "the reply had no usable brief"
        except Exception as e:  # the ruling form must still appear
            error = f"{type(e).__name__}: {e}"
        if error:
            logger.warning("Outcome dispute brief skipped: %s", error)

        result["briefs"] = briefs
        result["ruling_form"] = ruling_form(result["rows"], texts, briefs, change_line(context))
        context.set_process_property(result_key, result)
        output: dict[str, Any] = {"briefed": sorted(briefs, key=_sort_key)}
        if error:
            output["error"] = error[:500]
        return TaskResult.ok(output=output)

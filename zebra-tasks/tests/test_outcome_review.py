"""Tests for CompareOutcomeReviewsAction and its parsing (#190)."""

from unittest.mock import MagicMock

import pytest
from zebra.core.models import ProcessDefinition, ProcessInstance, TaskDefinition, TaskInstance
from zebra.forms import validate_form_data
from zebra.tasks.base import ExecutionContext

from zebra_tasks.agent import outcome_review
from zebra_tasks.agent.outcome_review import (
    MAX_BRIEF_CHARS,
    BriefOutcomeDisputesAction,
    CompareOutcomeReviewsAction,
    _verdict_labels,
    compare_reviews,
    first_sentence,
    outcome_ids,
    outcome_texts,
    parse_briefs,
    parse_review,
    record_ruling,
    ruling_form,
    takes_a_side,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage

_DEF = ProcessDefinition(
    id="d1", name="D", first_task_id="c", tasks={"c": TaskDefinition(id="c", name="C")}
)


def _context(properties: dict) -> ExecutionContext:
    return ExecutionContext(
        engine=MagicMock(),
        store=MagicMock(),
        process=ProcessInstance(id="p1", definition_id="d1", properties=properties),
        process_definition=_DEF,
        task_definition=_DEF.tasks["c"],
    )


def _task(**props) -> TaskInstance:
    return TaskInstance(
        id="t1", process_id="p1", task_definition_id="c", foe_id="f1", properties=props
    )


def _review(*verdicts: tuple[str, str]) -> dict:
    return {"verdicts": [{"id": i, "verdict": v, "evidence": f"{i} {v}"} for i, v in verdicts]}


@pytest.mark.parametrize(
    "value",
    [
        _review(("O1", "met")),
        _review(("O1", "met"))["verdicts"],
        '```json\n{"verdicts": [{"id": "o1", "verdict": "MET", "evidence": "O1 met"}]}\n```',
        '{"verdicts": [{"id": "O1", "verdict": "met", "evidence": "O1 met"}]}',
    ],
)
def test_parse_review_accepts_dicts_lists_and_json_text(value):
    assert parse_review(value) == {"O1": {"verdict": "met", "evidence": "O1 met"}}


@pytest.mark.parametrize("value", [None, "", "not json", 42, {"verdicts": "nope"}])
def test_unreadable_review_parses_to_nothing(value):
    assert parse_review(value) == {}


def test_unknown_verdict_is_kept_blank():
    assert parse_review(_review(("O1", "probably")))["O1"]["verdict"] == ""


def test_agreement_on_every_outcome():
    result = compare_reviews(
        parse_review(_review(("O1", "met"), ("O2", "partial"))),
        parse_review(_review(("O2", "partial"), ("O1", "met"))),
    )

    assert result["status"] == "agreed"
    assert result["disputed"] == []
    assert result["followups"] == ["O2"]
    assert [r["id"] for r in result["rows"]] == ["O1", "O2"]
    assert "| O2 | partial | partial | yes |" in result["table_markdown"]


@pytest.mark.parametrize(
    ("zebra", "claude"),
    [
        (_review(("O1", "met")), _review(("O1", "partial"))),
        (_review(("O1", "met")), _review(("O1", "met"), ("O2", "met"))),
        (_review(("O1", "probably")), _review(("O1", "probably"))),
        ("garbled", _review(("O1", "met"))),
    ],
)
def test_disagreement_missing_or_garbled_verdicts_are_disputed(zebra, claude):
    result = compare_reviews(parse_review(zebra), parse_review(claude))

    assert result["status"] == "disputed"
    assert result["disputed"]
    assert "**Claude:**" in result["dispute_notes"]


def test_no_verdicts_at_all_is_disputed():
    result = compare_reviews({}, {})

    assert result["status"] == "disputed"
    assert result["disputed"] == ["(no verdicts)"]


def test_outcomes_sort_numerically():
    result = compare_reviews(
        parse_review(_review(("O10", "met"), ("O2", "met"))),
        parse_review(_review(("O10", "met"), ("O2", "met"))),
    )

    assert [r["id"] for r in result["rows"]] == ["O2", "O10"]


async def test_action_routes_on_agreement():
    context = _context(
        {"zebra_review": _review(("O1", "met")), "claude_review": _review(("O1", "met"))}
    )

    result = await CompareOutcomeReviewsAction().run(_task(), context)

    assert result.next_route == "agreed"
    assert context.process.properties["review_result"]["status"] == "agreed"


async def test_reconsidered_verdicts_replace_the_first_ones():
    context = _context(
        {
            "zebra_review": _review(("O1", "met"), ("O2", "missed")),
            "zebra_reconsidered": _review(("O2", "partial")),
            "claude_review": _review(("O1", "met"), ("O2", "partial")),
        }
    )

    result = await CompareOutcomeReviewsAction().run(
        _task(reconsidered_key="zebra_reconsidered"), context
    )

    assert result.next_route == "agreed"
    assert result.output["followups"] == ["O2"]


async def test_ruling_records_the_human_decision_without_routing():
    context = _context(
        {
            "zebra_review": _review(("O1", "met")),
            "claude_review": _review(("O1", "missed")),
            "__task_output_human_ruling": {"ruling": "O1 missed: no tests"},
        }
    )

    result = await CompareOutcomeReviewsAction().run(_task(ruling_key="human_ruling"), context)

    assert result.next_route is None
    assert result.output["status"] == "ruled"
    assert result.output["ruling"] == "O1 missed: no tests"
    assert result.output["disputed"] == ["O1"]


OUTCOMES = """## Outcomes

| # | Outcome | How we'll know |
|---|---|---|
| O1 | Reviews compare | test |
| o2 | Disputes escalate | test |
Not a row | O9 |
"""


def test_outcome_ids_come_from_the_table_rows():
    assert outcome_ids(OUTCOMES) == {"O1", "O2"}
    assert outcome_ids(None) == set()


def test_an_outcome_neither_reviewer_judged_is_disputed():
    review = parse_review(_review(("O1", "met")))

    result = compare_reviews(review, review, outcome_ids(OUTCOMES))

    assert result["status"] == "disputed"
    assert result["disputed"] == ["O2"]
    assert "| O2 | ? | ? | **no** |" in result["table_markdown"]


async def test_action_compares_every_outcome_in_the_table():
    context = _context(
        {
            "outcomes": OUTCOMES,
            "zebra_review": _review(("O1", "met")),
            "claude_review": _review(("O1", "met")),
        }
    )

    result = await CompareOutcomeReviewsAction().run(_task(), context)

    assert result.next_route == "disputed"
    assert result.output["disputed"] == ["O2"]


def test_outcome_texts_come_from_the_second_cell():
    assert outcome_texts(OUTCOMES) == {"O1": "Reviews compare", "O2": "Disputes escalate"}


def test_dispute_notes_give_each_disputed_outcome_its_own_section():
    result = compare_reviews(
        parse_review(_review(("O1", "met"), ("O2", "met"))),
        parse_review(_review(("O1", "met"), ("O2", "partial"))),
        texts=outcome_texts(OUTCOMES),
    )

    sections = result["dispute_notes"].split("####")[1:]
    assert len(sections) == 1
    assert sections[0].startswith(" O2: Zebra met, Claude partial\n")
    assert "\n\n*Disputes escalate*\n\n" in sections[0]
    assert "\n\n**Zebra:** O2 met\n\n**Claude:** O2 partial" in sections[0]
    assert "O1" not in result["dispute_notes"]


def test_summary_names_each_outcome_without_evidence():
    result = compare_reviews(
        parse_review(_review(("O1", "met"), ("O2", "met"))),
        parse_review(_review(("O1", "met"), ("O2", "partial"))),
        texts=outcome_texts(OUTCOMES),
    )

    lines = result["summary_markdown"].splitlines()
    assert lines[0] == "| # | Outcome | Zebra | Claude | Agreed |"
    assert lines[2:] == [
        "| O1 | Reviews compare | met | met | yes |",
        "| O2 | Disputes escalate | met | partial | **no** |",
    ]
    assert "| O2 | met | partial | **no** | O2 met | O2 partial |" in result["table_markdown"]


async def test_action_names_outcomes_from_the_table():
    context = _context(
        {
            "outcomes": OUTCOMES,
            "zebra_review": _review(("O1", "met"), ("O2", "met")),
            "claude_review": _review(("O1", "met"), ("O2", "met")),
        }
    )

    result = await CompareOutcomeReviewsAction().run(_task(), context)

    assert "| O2 | Disputes escalate | met | met | yes |" in result.output["summary_markdown"]


async def test_final_step_records_without_routing():
    context = _context(
        {"zebra_review": _review(("O1", "met")), "claude_review": _review(("O1", "met"))}
    )

    result = await CompareOutcomeReviewsAction().run(_task(final=True), context)

    assert result.next_route is None
    assert context.process.properties["review_result"]["status"] == "agreed"


# --- Clearer ruling form (#295) -------------------------------------------------------------


def _rows(*triples: tuple[str, str, str]) -> list[dict]:
    """Rows from (id, zebra, claude) with evidence that names the side."""
    zebra = {i: {"verdict": z, "evidence": f"Zebra on {i}. Detail."} for i, z, _ in triples}
    claude = {i: {"verdict": c, "evidence": f"Claude on {i}; more."} for i, _, c in triples}
    return compare_reviews(zebra, claude)["rows"]


def test_first_sentence_cuts_at_the_first_full_stop_and_caps():
    assert first_sentence("See a.py:12. Then more.") == "See a.py:12."
    assert first_sentence("no stop here") == "no stop here"
    assert first_sentence("x" * 300, limit=10) == "x" * 9 + "…"
    assert first_sentence("") == ""


def test_ruling_form_has_a_section_and_a_required_pick_per_disputed_outcome():
    rows = _rows(("O1", "met", "met"), ("O2", "partial", "met"), ("O3", "met", "missed"))
    briefs = {
        "O2": {
            "crux": "Lock files",
            "zebra": "Skipped.",
            "claude": "Scanned.",
            "settle": "Run test_x.",
        }
    }

    form = ruling_form(rows, {"O2": "Scans everything"}, briefs, "#9 Scan (abc)")
    fields = form["properties"]

    assert form["title"] == "Zebra and Claude disagree on 2 of 3 outcomes"
    assert form["description"].startswith("#9 Scan (abc)\nPick a verdict")
    assert form["required"] == ["O2", "O3"]
    assert list(fields) == [
        "agreed",
        "O2_case",
        "O2",
        "O2_note",
        "O3_case",
        "O3",
        "O3_note",
        "notes",
        "evidence",
    ]
    assert fields["agreed"]["default"] == "O1 met"
    assert "O1" not in fields["evidence"]["default"]
    case = fields["O2_case"]["default"]
    assert case.startswith("*Scans everything*")
    assert "**In dispute:** Lock files" in case
    assert "| **Zebra** | partial | Skipped. |" in case
    assert "**What would settle it:** Run test_x." in case
    assert fields["O2"]["enum"] == ["met", "partial", "missed"]
    assert fields["O2"]["enumLabels"] == ["Met (Claude)", "Partial (Zebra)", "Missed"]
    # No brief for O3: each side's first sentence stands in, and no crux line
    assert "In dispute" not in fields["O3_case"]["default"]
    assert "| **Claude** | missed | Claude on O3; more. |" in fields["O3_case"]["default"]
    assert "| **Zebra** | met | Zebra on O3. |" in fields["O3_case"]["default"]


def test_a_shared_verdict_label_names_both_sides():
    (row,) = _rows(("O1", "", "met"))

    assert _verdict_labels(row) == ["Met (Claude)", "Partial", "Missed"]
    row["zebra"] = "met"
    assert _verdict_labels(row)[0] == "Met (Zebra and Claude)"


def test_ruling_form_text_cannot_inject_templates():
    """The form resolves {{templates}} in defaults; reviewer text must stay literal."""
    rows = compare_reviews(
        {"O1": {"verdict": "met", "evidence": "uses {{__secret__}}"}},
        {"O1": {"verdict": "missed", "evidence": "no"}},
    )["rows"]

    form = ruling_form(rows, {}, {"O1": {"crux": "{{x}}"}}, "#1 {{title}}")

    texts = [form["description"]] + [
        str(f.get(k, "")) for f in form["properties"].values() for k in ("default", "description")
    ]
    assert not [t for t in texts if "{{" in t or "}}" in t]
    assert "uses { {__secret__} }" in form["properties"]["evidence"]["default"]


def test_ruling_form_without_readable_verdicts_asks_in_words():
    form = compare_reviews({}, {})["ruling_form"]

    assert form["required"] == ["ruling"]
    assert form["properties"]["ruling"]["format"] == "multiline"


def test_a_ruling_without_a_pick_is_refused():
    form = ruling_form(_rows(("O1", "met", "partial")), {})

    errors = validate_form_data(form, {"O1": "", "O1_note": "x"})

    assert [e.field for e in errors] == ["O1"]
    assert validate_form_data(form, {"O1": "maybe"})
    assert validate_form_data(form, {"O1": "partial"}) == []


def test_record_ruling_sets_per_outcome_verdicts_and_followups():
    result = compare_reviews(
        {
            i: {"verdict": v, "evidence": ""}
            for i, v in [("O1", "partial"), ("O2", "met"), ("O3", "met")]
        },
        {
            i: {"verdict": v, "evidence": ""}
            for i, v in [("O1", "partial"), ("O2", "missed"), ("O3", "partial")]
        },
    )

    record_ruling(result, {"O2": "missed", "O2_note": " no  test ", "O3": "met", "notes": "ok"})

    assert result["status"] == "ruled"
    assert result["followups"] == ["O1", "O2"]  # agreed partial + ruled missed; ruled met is not
    assert result["ruling"] == "O2: missed: no test\nO3: met\nok"
    assert result["unruled"] == []
    rows = {r["id"]: r for r in result["rows"]}
    assert (rows["O2"]["ruling"], rows["O2"]["ruling_note"]) == ("missed", "no test")
    assert "| O2 | met | missed | **no** | **missed** (no test) |" in result["table_markdown"]
    assert "| O1 | partial | partial | yes | — |" in result["table_markdown"]


def test_record_ruling_keeps_a_free_text_answer_and_names_what_is_unruled():
    result = compare_reviews(
        {"O1": {"verdict": "met", "evidence": ""}}, {"O1": {"verdict": "missed", "evidence": ""}}
    )

    record_ruling(result, {"ruling": "Zebra is right"})

    assert result["ruling"] == "Zebra is right"
    assert result["unruled"] == ["O1"]
    assert result["followups"] == []
    assert "Ruling" not in result["table_markdown"]


@pytest.mark.parametrize(
    "text",
    [
        "Zebra is right: the lock files are skipped.",
        "Claude's correct about the tests.",
        "This should be partial.",
        "O1 must remain met.",
        "The correct verdict is missed.",
        "I recommend ruling for Zebra.",
        "We would rule partial.",
        "Rule in favour of Claude.",
    ],
)
def test_a_brief_that_takes_a_side_is_dropped(text):
    assert takes_a_side(text)
    reply = {"disputes": [{"id": "O1", "crux": "Lock files", "zebra": text, "settle": text}]}

    assert parse_briefs(reply, {"O1"}) == {"O1": {"crux": "Lock files"}}
    assert parse_briefs({"disputes": [{"id": "O1", "crux": text}]}, {"O1"}) == {}


@pytest.mark.parametrize(
    "text",
    [
        "Whether a pending prod check makes O1 partial or met",
        "Zebra says it is partial because lock lines skip the PII rules.",
        "Claude did not address the lock-file path.",
        "Read diff_scan.py:655-697 to see whether lock lines reach the PII rules.",
    ],
)
def test_describing_the_sides_is_not_taking_one(text):
    assert not takes_a_side(text)


def test_parse_briefs_keeps_only_disputed_ids_with_a_crux():
    reply = {
        "disputes": [
            {"id": "o1", "crux": " Lock\n files ", "zebra": "z", "claude": 3, "settle": "s"},
            {"id": "O2", "crux": "agreed one"},
            {"id": "O3", "zebra": "no crux"},
            "junk",
        ]
    }

    briefs = parse_briefs(reply, {"O1", "O3"})

    assert briefs == {"O1": {"crux": "Lock files", "zebra": "z", "settle": "s"}}
    assert parse_briefs("not json", {"O1"}) == {}
    assert (
        parse_briefs({"disputes": [{"id": "O1", "crux": "x" * 900}]}, {"O1"})["O1"]["crux"]
        == "x" * MAX_BRIEF_CHARS
    )


class _BriefLLM:
    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.calls: list[list] = []

    async def complete(self, messages, **kw):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return LLMResponse(
            content=self.reply,
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(10, 10),
            model="test/low",
        )


def _disputed_context() -> ExecutionContext:
    result = compare_reviews(
        parse_review(_review(("O1", "met"), ("O2", "met"))),
        parse_review(_review(("O1", "met"), ("O2", "partial"))),
        texts={"O1": "Reviews compare", "O2": "Disputes escalate"},
    )
    return _context(
        {
            "review_result": result,
            "outcomes": OUTCOMES,
            "issue": "295",
            "title": "Ruling form",
            "deployed_hash": "abc1234",
        }
    )


async def test_brief_action_puts_the_crux_in_the_form(monkeypatch):
    llm = _BriefLLM(
        '{"disputes": [{"id": "O2", "crux": "Is there a test?", "zebra": "Yes.",'
        ' "claude": "No.", "settle": "Run it."}]}'
    )
    tiers = []
    monkeypatch.setattr(outcome_review, "get_llm", lambda model, ctx: tiers.append(model) or llm)
    context = _disputed_context()

    result = await BriefOutcomeDisputesAction().run(_task(), context)

    assert result.success and result.output == {"briefed": ["O2"]}
    assert tiers == ["low"] and len(llm.calls) == 1
    system, user = (m.content for m in llm.calls[0])
    assert "NOT to decide it" in system
    assert "## O2: Disputes escalate" in user and "O2 partial" in user and "## O1" not in user
    stored = context.process.properties["review_result"]
    assert stored["briefs"]["O2"]["crux"] == "Is there a test?"
    form = stored["ruling_form"]
    assert form["description"].startswith("#295 Ruling form (abc1234)")
    assert "**In dispute:** Is there a test?" in form["properties"]["O2_case"]["default"]


@pytest.mark.parametrize(
    "reply", [RuntimeError("down"), "not json at all", '{"disputes": [{"id": "O9"}]}']
)
async def test_brief_action_never_fails(monkeypatch, reply):
    monkeypatch.setattr(outcome_review, "get_llm", lambda model, ctx: _BriefLLM(reply))
    context = _disputed_context()

    result = await BriefOutcomeDisputesAction().run(_task(), context)

    assert result.success
    assert result.output["briefed"] == [] and result.output["error"]
    stored = context.process.properties["review_result"]
    assert stored["briefs"] == {}
    assert (
        "| **Claude** | partial | O2 partial |"
        in (stored["ruling_form"]["properties"]["O2_case"]["default"])
    )


async def test_brief_action_without_an_llm_still_builds_the_form(monkeypatch):
    def no_llm(model, ctx):
        raise ValueError("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr(outcome_review, "get_llm", no_llm)
    context = _disputed_context()

    result = await BriefOutcomeDisputesAction().run(_task(), context)

    assert result.success and "OPENROUTER_API_KEY" in result.output["error"]
    assert context.process.properties["review_result"]["ruling_form"]["required"] == ["O2"]


async def test_brief_action_with_nothing_to_brief_is_a_no_op():
    result = await BriefOutcomeDisputesAction().run(_task(), _context({}))

    assert result.success and result.output["briefed"] == []


async def test_compare_carries_the_brief_into_the_recorded_result():
    context = _disputed_context()
    context.process.properties["review_result"]["briefs"] = {"O2": {"crux": "c"}}
    context.process.properties["zebra_review"] = _review(("O1", "met"), ("O2", "met"))
    context.process.properties["claude_review"] = _review(("O1", "met"), ("O2", "partial"))
    context.process.properties["__task_output_human_ruling"] = {"O2": "partial"}

    result = await CompareOutcomeReviewsAction().run(_task(ruling_key="human_ruling"), context)

    assert result.output["briefs"] == {"O2": {"crux": "c"}}
    assert result.output["followups"] == ["O2"]

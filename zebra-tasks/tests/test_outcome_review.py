"""Tests for CompareOutcomeReviewsAction and its parsing (#190)."""

from unittest.mock import MagicMock

import pytest
from zebra.core.models import ProcessDefinition, ProcessInstance, TaskDefinition, TaskInstance
from zebra.tasks.base import ExecutionContext

from zebra_tasks.agent.outcome_review import (
    CompareOutcomeReviewsAction,
    compare_reviews,
    parse_review,
)

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
    assert "Claude said" in result["dispute_notes"]


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


async def test_final_step_records_without_routing():
    context = _context(
        {"zebra_review": _review(("O1", "met")), "claude_review": _review(("O1", "met"))}
    )

    result = await CompareOutcomeReviewsAction().run(_task(final=True), context)

    assert result.next_route is None
    assert context.process.properties["review_result"]["status"] == "agreed"

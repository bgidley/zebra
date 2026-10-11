"""Tests for Zebra's voice layer read model and UI (#161)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.template.loader import render_to_string
from zebra_agent_web.api import thoughts as thoughts_mod
from zebra_agent_web.api.thoughts import Thought, recent_thoughts, thoughts_for_process

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

FULL_RUN = {
    "goal": "Draft the weekly progress digest",
    "run_id": "run-42",
    "ethics_input_assessment": {
        "approved": True,
        "overall_reasoning": "Writing a digest is fine.",
        "concerns": [],
    },
    "continuation_assessment": {"decision": "not_continuation"},
    "selection": {
        "workflow_name": "Summarize Text",
        "reasoning": "Closest match.",
        "voice": "I'm writing it from this week's activity log.",
        "confidence": 0.8,
    },
    "planning_concerns": {
        "concerns": [{"description": "Names a third party", "severity": "low"}],
        "summary": "One minor privacy concern.",
    },
    "ethics_plan_assessment": {
        "approved": True,
        "overall_reasoning": "Publishing is irreversible.",
        "concerns": ["Shared folder is public"],
        "voice": "Publishing is the one step I can't undo, so I'd rather ask.",
        "confidence": 0.6,
    },
    "ethics_post_assessment": {
        "ethical": True,
        "overall_reasoning": "Run was fine.",
        "concerns": [],
    },
}


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------


def test_thoughts_follow_step_order_and_skip_non_continuations():
    kinds = [t.kind for t in thoughts_for_process(FULL_RUN)]

    assert kinds == ["ethics_input", "selection", "concerns", "ethics_plan", "ethics_post"]


def test_voice_line_preferred_over_recorded_reasoning():
    by_kind = {t.kind: t for t in thoughts_for_process(FULL_RUN)}

    selection = by_kind["selection"]
    assert selection.is_voice is True
    assert selection.text == "I'm writing it from this week's activity log."
    assert selection.confidence == 0.8

    concerns = by_kind["concerns"]
    assert concerns.is_voice is False
    assert concerns.text == "One minor privacy concern."
    assert concerns.confidence is None  # nothing recorded, so no stripe


def test_quiet_when_nothing_notable_and_no_voice():
    by_kind = {t.kind: t for t in thoughts_for_process(FULL_RUN)}

    assert by_kind["ethics_input"].quiet is True  # approved, no concerns
    assert by_kind["ethics_post"].quiet is True
    assert by_kind["concerns"].quiet is False  # a concern was flagged
    assert by_kind["ethics_plan"].quiet is False  # has a voice line


def test_zero_confidence_is_kept():
    [thought] = thoughts_for_process({"selection": {"voice": "Unsure.", "confidence": 0.0}})

    assert thought.confidence == 0.0


def test_selection_without_voice_names_the_workflow():
    [thought] = thoughts_for_process(
        {"selection": {"workflow_name": "Web Research", "reasoning": "Needs fresh sources."}}
    )

    assert thought.text == "Web Research: Needs fresh sources."
    assert thought.is_voice is False


def test_continuation_rationale_is_not_repeated_by_selection():
    props = {
        "continuation_assessment": {"decision": "same_workflow", "rationale": "Retry the ranking."},
        "selection": {"workflow_name": "Brainstorm Ideas", "reasoning": "Retry the ranking."},
    }

    assert [t.kind for t in thoughts_for_process(props)] == ["continuation"]


@pytest.mark.parametrize(
    "props",
    [
        None,
        {},
        {"selection": "not a dict"},
        {"selection": {"reasoning": ""}},
        {"ethics_input_assessment": {"approved": True, "concerns": None}},
        {"selection": {"voice": "ok", "confidence": True}},
    ],
)
def test_malformed_or_empty_records_are_tolerated(props):
    result = thoughts_for_process(props)

    assert all(isinstance(t, Thought) for t in result)
    assert all(t.confidence is None for t in result)


# ---------------------------------------------------------------------------
# Feed query
# ---------------------------------------------------------------------------


def _process(pid, props, *, parent=None, user_id=None, minutes_ago=0):
    from zebra_agent_web.api.models import ProcessInstanceModel

    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return ProcessInstanceModel.objects.create(
        id=pid,
        definition_id="agent_main_loop",
        state="complete",
        user_id=user_id,
        properties=json.dumps(props),
        parent_process_id=parent,
        created_at=at,
        updated_at=at,
    )


@pytest.mark.django_db(transaction=True)
async def test_recent_thoughts_newest_run_first_skipping_quiet_and_children():
    from asgiref.sync import sync_to_async

    newer = {"goal": "Newer goal", "run_id": "run-2", **FULL_RUN}
    newer["goal"], newer["run_id"] = "Newer goal", "run-2"
    older = {
        "goal": "Older goal",
        "run_id": "run-1",
        "selection": {"workflow_name": "Web Research", "reasoning": "Fresh sources."},
    }
    await sync_to_async(_process)("p-old", older, parent="", minutes_ago=30)
    await sync_to_async(_process)("p-new", newer, parent=None, minutes_ago=1)
    await sync_to_async(_process)(
        "p-child", {"selection": {"voice": "child voice"}}, parent="p-new", minutes_ago=0
    )

    feed = await recent_thoughts(limit=10)

    texts = [item.thought.text for item in feed]
    assert "child voice" not in texts
    assert all(not item.thought.quiet for item in feed)
    # Newest run first, its latest step first.
    assert feed[0].goal == "Newer goal" and feed[0].thought.kind == "ethics_plan"
    assert feed[-1].goal == "Older goal" and feed[-1].run_id == "run-1"


@pytest.mark.django_db(transaction=True)
async def test_recent_thoughts_respects_limit_and_user(monkeypatch):
    from asgiref.sync import sync_to_async

    await sync_to_async(_process)("mine", FULL_RUN, user_id=1)
    await sync_to_async(_process)(
        "theirs", {"selection": {"voice": "not yours"}}, user_id=2, minutes_ago=0
    )
    monkeypatch.setattr("zebra_agent_web.middleware.get_current_user_id", lambda: 1)

    feed = await recent_thoughts(limit=2)

    assert len(feed) == 2
    assert all(item.run_id == "run-42" for item in feed)


@pytest.mark.django_db(transaction=True)
async def test_recent_thoughts_empty_for_user_without_runs(monkeypatch):
    from asgiref.sync import sync_to_async

    await sync_to_async(_process)("someone-else", FULL_RUN, user_id=2)
    monkeypatch.setattr("zebra_agent_web.middleware.get_current_user_id", lambda: 99)

    assert await recent_thoughts() == []


@pytest.mark.django_db(transaction=True)
async def test_recent_thoughts_skips_unparseable_rows(monkeypatch):
    async def rows(limit, user_id):
        return [("{not json", None), (json.dumps(FULL_RUN), None)]

    monkeypatch.setattr(thoughts_mod, "_recent_root_process_rows", rows)

    feed = await recent_thoughts()

    assert feed and feed[0].run_id == "run-42"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _thought(**overrides) -> Thought:
    base = dict(
        kind="selection",
        label="Workflow choice",
        task_id="select_workflow",
        text="I picked research.",
        is_voice=True,
        confidence=0.6,
    )
    return Thought(**{**base, **overrides})


def test_thought_component_voice_with_recorded_confidence():
    html = render_to_string("components/thought.html", {"thought": _thought()})

    assert "certainty-medium" in html
    assert "text-ink" in html
    assert "recorded reasoning" not in html


def test_thought_component_recorded_reasoning_without_confidence():
    html = render_to_string(
        "components/thought.html", {"thought": _thought(is_voice=False, confidence=None)}
    )

    assert "certainty" not in html  # no stripe without a recorded confidence
    assert "recorded reasoning" in html
    assert "text-muted" in html


def test_quiet_thought_renders_subdued():
    quiet = _thought(is_voice=False, confidence=None, quiet=True)

    assert "opacity-70" in render_to_string("components/thought.html", {"thought": quiet})
    assert "opacity-70" not in render_to_string("components/thought.html", {"thought": _thought()})


def test_thought_trail_renders_in_order_and_hides_when_empty():
    html = render_to_string(
        "partials/thought_trail.html", {"thoughts": thoughts_for_process(FULL_RUN)}
    )
    kinds = [
        k
        for k in ("ethics_input", "selection", "concerns", "ethics_plan", "ethics_post")
        if f'data-thought="{k}"' in html
    ]

    assert 'data-testid="thought-trail"' in html
    assert kinds == ["ethics_input", "selection", "concerns", "ethics_plan", "ethics_post"]
    assert render_to_string("partials/thought_trail.html", {"thoughts": []}).strip() == ""


def test_on_my_mind_links_runs_and_has_empty_state():
    feed = [
        thoughts_mod.FeedThought(thought=_thought(), goal="Compare libs", run_id="run-7", at=None)
    ]
    html = render_to_string("partials/on_my_mind.html", {"feed": feed})

    assert 'href="/runs/run-7/"' in html
    assert "Compare libs" in html

    empty = render_to_string("partials/on_my_mind.html", {"feed": []})
    assert "Nothing yet" in empty


def test_run_pages_include_the_thought_trail():
    for page in ("run_detail.html", "run_pending.html"):
        source = (TEMPLATES / "pages" / page).read_text()
        assert '{% include "partials/thought_trail.html" with thoughts=parent_flow.thoughts %}' in (
            source
        )


def test_knowledge_confidence_uses_certainty_stripes():
    html = render_to_string(
        "pages/knowledge_list.html",
        {
            "entries": [
                {
                    "id": "k1",
                    "category": "personal",
                    "key": "city",
                    "value": "Leeds",
                    "confidence": 0.5,
                    "source": "agent",
                    "last_verified": None,
                }
            ]
        },
    )
    cell = html.split('data-testid="knowledge-confidence"', 1)[1].split("</td>", 1)[0]

    assert "certainty-medium" in cell
    assert "0.50" in cell

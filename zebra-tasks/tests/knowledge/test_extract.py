"""Tests for ExtractKnowledgeAction and its helpers (F152)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra_agent.knowledge import KnowledgeEntry

from zebra_tasks.knowledge.extract import (
    ExtractKnowledgeAction,
    normalize_knowledge_key,
    resolve_raw,
    validate_candidates,
)
from zebra_tasks.llm.base import LLMResponse


def _make_context(properties=None, extras=None):
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = dict(properties or {})
    context.extras = extras or {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda t: t.replace("{{goal}}", "G"))
    return context


def _make_task(**props):
    task = MagicMock()
    task.id = "task-1"
    task.properties = props
    return task


def _provider(content):
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=content, model="haiku", usage={}, tool_calls=[], finish_reason="end_turn"
        )
    )
    return provider


def _candidates(*items):
    return json.dumps({"candidates": list(items)})


# --- helpers -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Employer", "employer"),
        ("Home City", "home_city"),
        ("user_employer", "employer"),
        ("my-partner's name", "partner_s_name"),
        ("  __Preferred  Language__ ", "preferred_language"),
        ("user_", "user"),
        (None, ""),
    ],
)
def test_normalize_knowledge_key(raw, expected):
    assert normalize_knowledge_key(raw) == expected


def test_normalize_truncates_long_keys():
    assert len(normalize_knowledge_key("a" * 200)) == 64


def test_validate_drops_invalid_secret_sensitive_and_low_confidence():
    raw = {
        "candidates": [
            {"category": "facts", "key": "Employer", "value": "Acme", "confidence": 0.9},
            {"category": "opinions", "key": "x", "value": "y", "confidence": 0.9},
            {"category": "facts", "key": "wifi_password", "value": "hunter2", "confidence": 1},
            {"category": "facts", "key": "card", "value": "4111 1111 1111 1111", "confidence": 1},
            {
                "category": "facts",
                "key": "condition",
                "value": "diabetes",
                "confidence": 0.9,
                "sensitive": True,
            },
            {"category": "facts", "key": "maybe", "value": "z", "confidence": 0.2},
            {"category": "facts", "key": "employer", "value": "Acme Ltd", "confidence": 0.9},
        ]
    }
    kept, dropped = validate_candidates(raw)
    assert [c["key"] for c in kept] == ["employer"]
    assert kept[0]["value"] == "Acme"
    reasons = sorted(d["reason"] for d in dropped)
    assert reasons == [
        "duplicate",
        "invalid_category",
        "low_confidence",
        "secret",
        "secret",
        "sensitive",
    ]


def test_validate_keeps_sensitive_when_opted_in():
    raw = [
        {"category": "facts", "key": "religion", "value": "x", "confidence": 0.9, "sensitive": 1}
    ]
    kept, _ = validate_candidates(raw, allow_sensitive=True)
    assert len(kept) == 1


def test_validate_caps_entries():
    raw = [{"category": "facts", "key": f"k{i}", "value": "v", "confidence": 0.9} for i in range(8)]
    kept, dropped = validate_candidates(raw, max_entries=3)
    assert len(kept) == 3
    assert [d["reason"] for d in dropped] == ["cap"] * 5


def test_resolve_raw_keeps_structure():
    context = _make_context({"execution_result": {"user_inputs": {"Ask": {"a": 1}}}})
    assert resolve_raw(context, "{{execution_result.user_inputs}}") == {"Ask": {"a": 1}}
    assert resolve_raw(context, ["x"]) == ["x"]


# --- action ------------------------------------------------------------------


async def test_skips_without_user_and_makes_no_llm_call():
    context = _make_context({"goal": "I work at Acme"})
    with patch("zebra_tasks.knowledge.extract.get_provider") as gp:
        result = await ExtractKnowledgeAction().run(_make_task(goal="I work at Acme"), context)
    gp.assert_not_called()
    assert result.success
    assert result.next_route == "no_candidates"
    assert result.output["skipped"] == "no_user"
    assert context.process.properties["knowledge_candidates"]["count"] == 0


async def test_skips_without_user_text():
    context = _make_context({"__user_id__": 1})
    with patch("zebra_tasks.knowledge.extract.get_provider") as gp:
        result = await ExtractKnowledgeAction().run(_make_task(goal=""), context)
    gp.assert_not_called()
    assert result.output["skipped"] == "no_user_text"


async def test_extracts_candidates_and_offers_existing_keys():
    existing = KnowledgeEntry.create(user_id=1, category="facts", key="home_city", value="Leeds")
    store = MagicMock()
    store.get_entries = AsyncMock(return_value=[existing])
    context = _make_context({"__user_id__": 1}, {"__knowledge_store__": store})
    provider = _provider(
        "```json\n"
        + _candidates(
            {
                "category": "facts",
                "key": "Employer",
                "value": "Acme",
                "time_sensitive": True,
                "confidence": 0.9,
            },
            {"category": "facts", "key": "home city", "value": "York", "confidence": 0.8},
        )
        + "\n```"
    )
    task = _make_task(
        goal="I work at Acme, plan my commute",
        user_inputs={"Where from?": {"origin": "York"}},
        continuation_comment="",
        result="Take the 8:05 train",
    )
    with patch("zebra_tasks.knowledge.extract.get_provider", return_value=provider):
        result = await ExtractKnowledgeAction().run(task, context)

    assert result.next_route == "has_candidates"
    cands = result.output["candidates"]
    assert cands[0] == {
        "category": "facts",
        "key": "employer",
        "value": "Acme",
        "time_sensitive": True,
        "confidence": 0.9,
        "existing_key": False,
    }
    assert cands[1]["key"] == "home_city" and cands[1]["existing_key"] is True
    prompt = provider.complete.call_args.kwargs["messages"][1].content
    assert "facts/home_city: Leeds" in prompt
    assert "I work at Acme" in prompt
    assert '"origin": "York"' in prompt


async def test_nothing_personal_yields_no_candidates():
    context = _make_context({"__user_id__": 1})
    with patch(
        "zebra_tasks.knowledge.extract.get_provider",
        return_value=_provider(_candidates()),
    ):
        result = await ExtractKnowledgeAction().run(_make_task(goal="Summarise this text"), context)
    assert result.next_route == "no_candidates"
    assert result.output["candidates"] == []


async def test_llm_error_degrades_to_empty():
    context = _make_context({"__user_id__": 1})
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("zebra_tasks.knowledge.extract.get_provider", return_value=provider):
        result = await ExtractKnowledgeAction().run(_make_task(goal="I live in Leeds"), context)
    assert result.success
    assert result.next_route == "no_candidates"
    assert "boom" in result.output["skipped"]


async def test_unparseable_response_degrades_to_empty():
    context = _make_context({"__user_id__": 1})
    with patch("zebra_tasks.knowledge.extract.get_provider", return_value=_provider("not json")):
        result = await ExtractKnowledgeAction().run(_make_task(goal="I live in Leeds"), context)
    assert result.success
    assert result.output["count"] == 0


async def test_sensitive_opt_in_via_env(monkeypatch):
    monkeypatch.setenv("ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE", "true")
    context = _make_context({"__user_id__": 1})
    content = _candidates(
        {"category": "facts", "key": "faith", "value": "x", "confidence": 0.9, "sensitive": True}
    )
    with patch("zebra_tasks.knowledge.extract.get_provider", return_value=_provider(content)):
        result = await ExtractKnowledgeAction().run(_make_task(goal="..."), context)
    assert result.output["count"] == 1


async def test_sensitive_dropped_by_default():
    context = _make_context({"__user_id__": 1})
    content = _candidates(
        {"category": "facts", "key": "faith", "value": "x", "confidence": 0.9, "sensitive": True}
    )
    with patch("zebra_tasks.knowledge.extract.get_provider", return_value=_provider(content)):
        result = await ExtractKnowledgeAction().run(_make_task(goal="..."), context)
    assert result.output["count"] == 0
    assert result.output["dropped"][0]["reason"] == "sensitive"

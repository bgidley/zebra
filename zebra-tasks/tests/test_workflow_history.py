"""Tests for workflow history actions (F138)."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.history import (
    MAX_CONTEXT_CHARS,
    MAX_FIELD_CHARS,
    AssessHistoryNeedAction,
    GetWorkflowHistoryAction,
    parse_time,
    with_workflow_history,
)

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


@dataclass
class _Run:
    id: str
    workflow_name: str
    goal: str
    started_at: datetime
    success: bool = True
    user_rating: int | None = None
    output: Any = None
    error: str | None = None


def _task(**props):
    task = MagicMock()
    task.id = "task-1"
    task.properties = props
    return task


@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.process.id = "proc-1"
    ctx.process.properties = {"__user_id__": 42, "run_id": "current"}
    ctx.extras = {}
    ctx.get_process_property = MagicMock(
        side_effect=lambda k, d=None: ctx.process.properties.get(k, d)
    )
    ctx.set_process_property = MagicMock(
        side_effect=lambda k, v: ctx.process.properties.__setitem__(k, v)
    )
    ctx.resolve_template = MagicMock(side_effect=lambda x: x)
    return ctx


def _store(runs):
    store = MagicMock()
    store.search_runs = AsyncMock(return_value=runs)
    return store


class TestParseTime:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("-7d", NOW - timedelta(days=7)),
            ("7d", NOW - timedelta(days=7)),
            ("24h", NOW - timedelta(hours=24)),
            ("-30m", NOW - timedelta(minutes=30)),
            ("2w", NOW - timedelta(weeks=2)),
            ("+1d", NOW + timedelta(days=1)),
        ],
    )
    def test_relative(self, value, expected):
        assert parse_time(value, now=NOW) == expected

    def test_iso_with_z(self):
        assert parse_time("2026-10-01T09:00:00Z") == datetime(2026, 10, 1, 9, tzinfo=UTC)

    def test_naive_iso_is_utc(self):
        assert parse_time("2026-10-01").tzinfo == UTC

    @pytest.mark.parametrize("value", [None, "", "  ", "None"])
    def test_empty_is_none(self, value):
        assert parse_time(value) is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="last tuesday"):
            parse_time("last tuesday")


class TestGetWorkflowHistory:
    async def test_relative_window_and_text(self, context):
        runs = [_Run("r1", "Research", "Compare pension providers", NOW, output="Vanguard")]
        store = _store(runs)
        context.extras["__metrics_store__"] = store

        result = await GetWorkflowHistoryAction().run(_task(since="-7d", text="pension"), context)

        assert result.success
        assert result.output["count"] == 1
        assert result.output["runs"][0]["goal"] == "Compare pension providers"
        kwargs = store.search_runs.call_args.kwargs
        assert kwargs["text"] == "pension"
        assert kwargs["user_id"] == 42
        expected_since = datetime.now(UTC) - timedelta(days=7)
        assert abs(kwargs["since"] - expected_since) < timedelta(seconds=5)
        assert result.output["filters"]["since"] == kwargs["since"].isoformat()
        assert "Vanguard" in result.output["history_context"]
        assert context.process.properties["workflow_history"] == result.output

    async def test_no_matches(self, context):
        context.extras["__metrics_store__"] = _store([])
        result = await GetWorkflowHistoryAction().run(_task(text="zzz"), context)
        assert result.success
        assert result.output["count"] == 0
        assert result.output["runs"] == []
        assert "No matching workflow history" in result.output["history_context"]

    async def test_store_unavailable(self, context, caplog):
        result = await GetWorkflowHistoryAction().run(_task(since="-1d"), context)
        assert result.success
        assert result.output["count"] == 0
        assert "no metrics store" in caplog.text

    async def test_invalid_time_fails(self, context):
        context.extras["__metrics_store__"] = _store([])
        result = await GetWorkflowHistoryAction().run(_task(since="whenever"), context)
        assert not result.success
        assert "whenever" in result.error

    async def test_excludes_current_run(self, context):
        runs = [_Run("current", "W", "this goal", NOW), _Run("old", "W", "older", NOW)]
        context.extras["__metrics_store__"] = _store(runs)
        result = await GetWorkflowHistoryAction().run(_task(limit=5), context)
        assert [r["id"] for r in result.output["runs"]] == ["old"]
        assert context.extras["__metrics_store__"].search_runs.call_args.kwargs["limit"] == 6

    async def test_output_is_bounded(self, context):
        big = "x" * 5000
        runs = [_Run(f"r{i}", "W", f"goal {i}", NOW, output=big) for i in range(50)]
        context.extras["__metrics_store__"] = _store(runs)
        result = await GetWorkflowHistoryAction().run(_task(limit=50), context)
        assert all(len(r["output"]) <= MAX_FIELD_CHARS for r in result.output["runs"])
        assert len(result.output["history_context"]) <= MAX_CONTEXT_CHARS + 100
        assert "more run(s) omitted" in result.output["history_context"]

    async def test_output_is_json_serialisable(self, context):
        runs = [_Run("r1", "W", "g", NOW, output={"answer": 1}, user_rating=4)]
        context.extras["__metrics_store__"] = _store(runs)
        result = await GetWorkflowHistoryAction().run(_task(), context)
        json.dumps(result.output)

    async def test_empty_templates_mean_no_filter(self, context):
        store = _store([])
        context.extras["__metrics_store__"] = store
        context.resolve_template = MagicMock(return_value="")
        await GetWorkflowHistoryAction().run(_task(since="{{h.since}}", text="{{h.text}}"), context)
        kwargs = store.search_runs.call_args.kwargs
        assert kwargs["since"] is None and kwargs["text"] is None


def _provider(content: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=MagicMock(content=content, model="haiku"))
    return provider


class TestAssessHistoryNeed:
    async def test_goal_referencing_past_work(self, context):
        since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        content = json.dumps(
            {"needs_history": True, "since": "-7d", "until": None, "text": "pensions"}
        )
        with patch("zebra_tasks.agent.history.get_provider", return_value=_provider(content)) as gp:
            result = await AssessHistoryNeedAction().run(
                _task(goal="what did I ask you about pensions last week?"), context
            )
        assert result.next_route == "needs_history"
        assert result.output["text"] == "pensions"
        assert result.output["since"][:13] == since[:13]
        assert gp.call_args.args[1] == "haiku"
        assert context.process.properties["history_need"]["needs_history"] is True

    async def test_ordinary_goal_skips_llm(self, context):
        with patch("zebra_tasks.agent.history.get_provider") as gp:
            result = await AssessHistoryNeedAction().run(
                _task(goal="write a haiku about autumn"), context
            )
        assert result.next_route == "no_history"
        gp.assert_not_called()

    async def test_llm_says_no(self, context):
        provider = _provider('```json\n{"needs_history": false, "reasoning": "topic"}\n```')
        with patch("zebra_tasks.agent.history.get_provider", return_value=provider):
            result = await AssessHistoryNeedAction().run(
                _task(goal="explain the history of Rome"), context
            )
        assert result.next_route == "no_history"

    async def test_llm_failure_degrades(self, context):
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("zebra_tasks.agent.history.get_provider", return_value=provider):
            result = await AssessHistoryNeedAction().run(
                _task(goal="what did we do yesterday?"), context
            )
        assert result.success
        assert result.next_route == "no_history"

    async def test_unparseable_degrades(self, context):
        with patch("zebra_tasks.agent.history.get_provider", return_value=_provider("nope")):
            result = await AssessHistoryNeedAction().run(
                _task(goal="have we tried this before?"), context
            )
        assert result.next_route == "no_history"

    async def test_bad_extracted_time_is_dropped(self, context):
        provider = _provider(json.dumps({"needs_history": True, "since": "last tuesday"}))
        with patch("zebra_tasks.agent.history.get_provider", return_value=provider):
            result = await AssessHistoryNeedAction().run(
                _task(goal="what did I ask last tuesday?"), context
            )
        assert result.next_route == "needs_history"
        assert result.output["since"] is None


class TestWithWorkflowHistory:
    def test_goal_unchanged_without_history(self):
        assert with_workflow_history("do it", {}) == "do it"
        assert with_workflow_history("do it", {"workflow_history": {"runs": []}}) == "do it"

    def test_goal_augmented_with_history(self):
        props = {"workflow_history": {"history_context": "- [2026-10-01] Research: pensions"}}
        goal = with_workflow_history("what did I ask?", props)
        assert goal.startswith("what did I ask?\n")
        assert "<workflow_history>\n- [2026-10-01] Research: pensions\n</workflow_history>" in goal

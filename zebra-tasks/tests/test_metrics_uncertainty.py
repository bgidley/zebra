"""Workflow health metrics report sample sizes and uncertainty (#328)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from zebra_agent.metrics import WorkflowRun
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.agent.analyzer import MetricsAnalyzerAction
from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction


def _runs(workflow: str, successes: int, failures: int, days_ago: float = 0.1):
    started = datetime.now() - timedelta(days=days_ago)
    return [
        WorkflowRun(
            id=f"{workflow}-{i}",
            workflow_name=workflow,
            goal=f"goal {workflow} {i}",
            started_at=started,
            completed_at=started,
            success=i < successes,
        )
        for i in range(successes + failures)
    ]


async def _analyze(*runs: WorkflowRun) -> dict:
    store = InMemoryMetricsStore()
    await store.initialize()
    for run in runs:
        await store.record_run(run)
    task = MagicMock()
    task.properties = {"days_to_analyze": 7, "min_runs_for_analysis": 3}
    ctx = MagicMock()
    ctx.process.properties = {}
    ctx.extras = {"__metrics_store__": store}
    ctx.set_process_property = MagicMock()
    action = MetricsAnalyzerAction()
    return await action._analyze_metrics(store, 7, 3)


def _by_name(analysis: dict) -> dict:
    return {w["workflow_name"]: w for w in analysis["workflow_stats"]}


async def test_stats_carry_successes_runs_and_interval():
    stats = _by_name(await _analyze(*_runs("Tiny", 3, 0)))["Tiny"]

    assert (stats["successful_runs"], stats["total_runs"]) == (3, 3)
    assert stats["success_rate"] == 1.0
    assert stats["success_ci_low"] == pytest.approx(0.4385, abs=1e-3)
    assert stats["success_ci_high"] == pytest.approx(1.0)
    assert stats["confidence"] == "adequate"


async def test_zero_run_two_run_and_twenty_run_workflows_are_distinguished():
    old = _runs("Idle", 2, 0, days_ago=30)
    analysis = await _analyze(*old, *_runs("Thin", 2, 0), *_runs("Busy", 18, 2))
    stats = _by_name(analysis)

    assert stats["Idle"]["confidence"] == "none"
    assert stats["Idle"]["total_runs"] == 0
    assert stats["Idle"]["success_rate"] is None
    assert stats["Idle"]["success_ci_low"] is None
    assert stats["Thin"]["confidence"] == "insufficient"
    assert stats["Busy"]["confidence"] == "adequate"
    assert analysis["workflows_without_runs"] == 1
    assert analysis["unique_workflows"] == 2
    assert analysis["workflow_stats"][-1]["workflow_name"] == "Idle"


async def test_small_perfect_sample_is_not_a_high_performer():
    analysis = await _analyze(*_runs("Tiny", 3, 0), *_runs("Solid", 40, 0))

    assert [w["workflow_name"] for w in analysis["high_performers"]] == ["Solid"]


async def test_high_performer_keeps_the_point_rate_cutoff():
    # 75% over 400 runs has a lower bound above 0.7 but is not >= 90%: not high
    # 9/10 has a lower bound near 0.6: not high either; both pinned deliberately
    analysis = await _analyze(*_runs("Big75", 300, 100), *_runs("Nine10", 9, 1))

    assert analysis["high_performers"] == []
    assert [w["workflow_name"] for w in analysis["low_performers"]] == []


async def test_low_performer_rule_is_the_point_rate_with_enough_runs():
    analysis = await _analyze(*_runs("Two3", 2, 1), *_runs("Zero2", 0, 2))

    assert [w["workflow_name"] for w in analysis["low_performers"]] == ["Two3"]
    assert analysis["high_performers"] == []


async def test_new_fields_are_additive():
    analysis = await _analyze(*_runs("Research", 2, 2))
    stats = _by_name(analysis)["Research"]

    for key in (
        "workflow_name",
        "total_runs",
        "success_rate",
        "avg_rating",
        "avg_tokens",
        "last_used",
        "continued_runs",
        "continuation_rate",
    ):
        assert key in stats
    assert stats["success_rate"] == 0.5


async def test_prompt_shows_counts_interval_and_tags():
    analysis = await _analyze(*_runs("Idle", 2, 0, days_ago=30), *_runs("Thin", 2, 0))
    prompt = WorkflowEvaluatorAction()._build_prompt(analysis, {})

    assert "- Thin: 2/2 successes (100%, 95% CI 34-100%) [insufficient data]" in prompt
    assert "- Idle: 0 runs, no success rate [no data]" in prompt


def test_system_prompt_tells_model_not_to_judge_thin_data():
    text = WorkflowEvaluatorAction.SYSTEM_PROMPT

    assert "do not assess their health" in text
    assert "state the sample size" in text


def test_prompt_builds_for_stats_without_the_new_keys():
    stat = {"workflow_name": "Old", "total_runs": 4, "success_rate": 0.5, "avg_rating": None}
    prompt = WorkflowEvaluatorAction()._build_prompt(
        {"total_runs_analyzed": 4, "workflow_stats": [stat]}, {}
    )

    assert "- Old: 2/4 successes (50%)" in prompt

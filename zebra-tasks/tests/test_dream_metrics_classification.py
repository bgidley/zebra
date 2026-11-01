"""Dream metrics analysis tells goal, tool and system runs apart (#256)."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.metrics import WorkflowRun
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.agent.analyzer import MetricsAnalyzerAction
from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction
from zebra_tasks.agent.leak_guard import run_texts_from_metrics
from zebra_tasks.agent.run_kinds import TOOL_GOAL_PREFIX

MISS = "'zebra-tasks/nope.py' does not exist. Use list_zebra_source to see what exists."
CRASH = "Task read_source failed: KeyError: 'path'"


@pytest.fixture
def task():
    t = MagicMock()
    t.properties = {"days_to_analyze": 7, "min_runs_for_analysis": 1}
    return t


@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.process.properties = {}
    ctx.extras = {}
    ctx.set_process_property = MagicMock(
        side_effect=lambda k, v: ctx.process.properties.__setitem__(k, v)
    )
    return ctx


def _run(run_id, workflow, success=True, tool=False, error=None, hours_ago=1) -> WorkflowRun:
    started = datetime.now() - timedelta(hours=hours_ago)
    goal = f"{TOOL_GOAL_PREFIX}read something" if tool else f"goal {run_id}"
    return WorkflowRun(
        id=run_id,
        workflow_name=workflow,
        goal=goal,
        started_at=started,
        completed_at=started,
        success=success,
        error=error,
    )


async def _store(*runs: WorkflowRun) -> InMemoryMetricsStore:
    store = InMemoryMetricsStore()
    await store.initialize()
    for run in runs:
        await store.record_run(run)
    return store


def _library(*workflows: tuple[str, list[str]]) -> MagicMock:
    library = MagicMock()
    library.list_workflows = AsyncMock(
        return_value=[SimpleNamespace(name=n, tags=tags) for n, tags in workflows]
    )
    return library


async def _analyze(store, task, context, library=None) -> dict:
    context.extras["__metrics_store__"] = store
    if library is not None:
        context.extras["__workflow_library__"] = library
    result = await MetricsAnalyzerAction().run(task, context)
    assert result.success, result.error
    json.dumps(result.output)  # stored as a process property
    return result.output


def _mixed_runs() -> list[WorkflowRun]:
    return [
        _run("g1", "Research"),
        _run("g2", "Research", success=False, error="LLM said no"),
        *[_run(f"t{i}", "Read Zebra Source", tool=True) for i in range(10)],
        _run("l1", "List Zebra Source", tool=True),
        _run("l2", "List Zebra Source", tool=True),
        _run("l3", "List Zebra Source", tool=True),
        _run("l4", "List Zebra Source", success=False, tool=True, error=MISS),
        _run("l5", "List Zebra Source", success=False, tool=True, error=MISS),
        _run("l6", "List Zebra Source", success=False, tool=True, error=CRASH),
        _run("s1", "Outcome Review", success=False, error="review crashed"),
    ]


class TestAnalyzerSplit:
    async def test_goal_statistics_hold_only_goal_runs(self, task, context):
        library = _library(("Outcome Review", ["review", "system"]), ("Research", []))
        analysis = await _analyze(await _store(*_mixed_runs()), task, context, library)

        assert [w["workflow_name"] for w in analysis["workflow_stats"]] == ["Research"]
        research = analysis["workflow_stats"][0]
        assert (research["total_runs"], research["success_rate"]) == (2, 0.5)
        assert [w["workflow_name"] for w in analysis["low_performers"]] == ["Research"]
        assert analysis["high_performers"] == []
        assert [p["workflow_name"] for p in analysis["failure_patterns"]] == ["Research"]
        assert analysis["unrated_runs_count"] == 2
        assert analysis["usage_trends"]["most_used"] == [{"workflow": "Research", "count": 2}]
        assert analysis["unique_workflows"] == 1
        assert not any("Zebra Source" in r for r in analysis["recommendations"])

    async def test_run_counts_reconcile(self, task, context):
        library = _library(("Outcome Review", ["system"]))
        analysis = await _analyze(await _store(*_mixed_runs()), task, context, library)

        counts = analysis["run_counts"]
        assert counts == {"goal": 2, "tool": 16, "system": 1, "expected_misses": 2}
        assert counts["goal"] + counts["tool"] + counts["system"] == analysis["total_runs_analyzed"]

    async def test_tool_workflows_count_misses_apart_from_failures(self, task, context):
        analysis = await _analyze(await _store(*_mixed_runs()), task, context)

        by_name = {t["workflow_name"]: t for t in analysis["tool_workflow_stats"]}
        assert by_name["List Zebra Source"] == {
            "workflow_name": "List Zebra Source",
            "total_runs": 6,
            "successful_runs": 3,
            "expected_misses": 2,
            "failures": 1,
            "success_rate": 0.75,
        }
        assert by_name["Read Zebra Source"]["success_rate"] == 1.0
        patterns = analysis["tool_failure_patterns"]
        assert [(p["workflow_name"], p["failure_count"]) for p in patterns] == [
            ("List Zebra Source", 1)
        ]
        assert list(patterns[0]["error_types"]) == [CRASH[:50]]

    async def test_all_misses_have_no_success_rate(self, task, context):
        store = await _store(
            _run("m1", "List Zebra Source", success=False, tool=True, error=MISS),
            _run("m2", "List Zebra Source", success=False, tool=True, error=MISS),
        )
        analysis = await _analyze(store, task, context)

        (stats,) = analysis["tool_workflow_stats"]
        assert (stats["expected_misses"], stats["failures"]) == (2, 0)
        assert stats["success_rate"] is None
        assert analysis["tool_failure_patterns"] == []

    async def test_a_goal_run_with_miss_text_is_still_a_failure(self, task, context):
        store = await _store(_run("g1", "Research", success=False, error=MISS))
        analysis = await _analyze(store, task, context)

        assert analysis["run_counts"]["expected_misses"] == 0
        assert analysis["failure_patterns"][0]["failure_count"] == 1

    async def test_system_workflows_are_reported_apart(self, task, context):
        library = _library(("Outcome Review", ["system"]))
        analysis = await _analyze(await _store(*_mixed_runs()), task, context, library)

        (system,) = analysis["system_workflow_stats"]
        assert (system["workflow_name"], system["total_runs"]) == ("Outcome Review", 1)
        names = {w["workflow_name"] for w in analysis["low_performers"]}
        assert "Outcome Review" not in names

    async def test_without_library_nothing_is_system(self, task, context):
        analysis = await _analyze(await _store(*_mixed_runs()), task, context)

        assert analysis["run_counts"]["system"] == 0
        assert analysis["system_workflow_stats"] == []
        assert {w["workflow_name"] for w in analysis["workflow_stats"]} == {
            "Research",
            "Outcome Review",
        }

    async def test_a_broken_library_degrades_to_no_system(self, task, context):
        library = MagicMock()
        library.list_workflows = AsyncMock(side_effect=RuntimeError("db down"))
        analysis = await _analyze(await _store(*_mixed_runs()), task, context, library)

        assert analysis["run_counts"]["system"] == 0


class TestEvaluatorPrompt:
    async def test_prompt_shows_the_split(self, task, context):
        library = _library(("Outcome Review", ["system"]))
        analysis = await _analyze(await _store(*_mixed_runs()), task, context, library)

        prompt = WorkflowEvaluatorAction()._build_prompt(analysis, {})

        assert "Goal runs: 2, tool calls by agents: 16, system runs: 1" in prompt
        assert "### Workflow Statistics (goal runs)\n- Research: 2 runs, 50% success" in prompt
        assert (
            "- List Zebra Source: 6 calls, 2 expected misses, 1 failures, "
            "75% success excluding misses"
        ) in prompt
        assert "### Tool Failure Patterns\n- List Zebra Source: 1 failures" in prompt
        assert MISS[:50] not in prompt
        assert CRASH[:50] in prompt

    def test_prompt_without_the_new_keys_still_builds(self):
        prompt = WorkflowEvaluatorAction()._build_prompt(
            {"total_runs_analyzed": 1, "workflow_stats": []}, {}
        )

        assert "Tool Workflows" not in prompt
        assert "Goal runs:" not in prompt


def test_leak_guard_sees_tool_failure_text():
    analysis = {
        "failure_patterns": [],
        "tool_failure_patterns": [
            {
                "workflow_name": "List Zebra Source",
                "failure_count": 1,
                "error_types": {CRASH: 1},
                "sample_goals": ["[tool] read Acme Ltd invoices"],
            }
        ],
    }

    texts = run_texts_from_metrics(analysis)

    assert "[tool] read Acme Ltd invoices" in texts
    assert CRASH in texts

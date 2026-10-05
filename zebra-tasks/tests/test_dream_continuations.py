"""Tests for dream-cycle continuation analysis (F136, GitLab #136).

Seeds continuation chains into an InMemoryMetricsStore and drives the
metrics_analyzer -> workflow_evaluator -> workflow_optimizer actions.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.metrics import TaskExecution, WorkflowRun
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.agent.analyzer import MetricsAnalyzerAction
from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction
from zebra_tasks.agent.optimizer import WorkflowOptimizerAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage

_REPORT_YAML = """name: Write Report
description: Draft a report
use_when: User wants a report
first_task: draft
tasks:
  draft:
    name: Draft
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
"""

_BAD_ROUTING_YAML = _REPORT_YAML + "routings:\n  - from: draft\n    to: missing_task\n"


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    context.engine.actions.has_action = MagicMock(side_effect=lambda name: name == "llm_call")
    context.engine.actions.format_for_prompt = MagicMock(return_value="")
    return context


def _response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


def _run(run_id, workflow, hours_ago, success=True, extends=None, **lineage) -> WorkflowRun:
    started = datetime.now() - timedelta(hours=hours_ago)
    return WorkflowRun(
        id=run_id,
        workflow_name=workflow,
        goal=f"goal for {run_id}",
        started_at=started,
        completed_at=started,
        success=success,
        extends_run_id=extends,
        **lineage,
    )


def _tasks(run_id: str, *steps: tuple[str, str, str]) -> list[TaskExecution]:
    out = []
    for order, (tid, name, state) in enumerate(steps, start=1):
        e = TaskExecution.create(run_id, tid, name, order)
        e.state = state
        out.append(e)
    return out


async def _plain_store() -> InMemoryMetricsStore:
    store = InMemoryMetricsStore()
    await store.initialize()
    for i in range(3):
        await store.record_run(_run(f"p{i}", "Answer Question", hours_ago=i + 1))
    return store


@pytest.fixture
async def seeded_store() -> InMemoryMetricsStore:
    """Write Report continued twice into Proofread Report; Answer Question needed a
    new workflow (Build Chart), which was itself continued without lineage detail."""
    store = InMemoryMetricsStore()
    await store.initialize()
    runs = [
        _run("r1", "Write Report", 30),
        _run("r2", "Write Report", 28),
        _run("r3", "Write Report", 26),
        _run("r4", "Write Report", 24),
        _run(
            "c1",
            "Proofread Report",
            20,
            extends="r1",
            continuation_comment="also proofread it",
            continuation_decision="existing_workflow",
            continuation_rationale="Proofread Report covers this",
        ),
        _run(
            "c2",
            "Proofread Report",
            18,
            extends="r2",
            continuation_comment="please proofread before sending",
            continuation_decision="existing_workflow",
        ),
        _run("a1", "Answer Question", 16, success=False),
        _run(
            "n1",
            "Build Chart",
            12,
            extends="a1",
            continuation_comment="draw a chart of the numbers",
            continuation_decision="new_workflow",
            continuation_rationale="no charting workflow existed",
        ),
        _run("n2", "Build Chart", 8, extends="n1"),  # lineage detail not yet populated
    ]
    for r in runs:
        await store.record_run(r)

    executions = {
        "r1": [("draft", "Draft", "complete")],
        "r2": [("draft", "Draft", "complete")],
        "c1": [("proofread", "Proofread", "complete")],
        "c2": [("proofread", "Proofread", "complete")],
        "a1": [("answer", "Answer", "complete"), ("format", "Format", "failed")],
        "n1": [("chart", "Render Chart", "complete")],
        "n2": [("chart", "Render Chart", "complete")],
    }
    for run_id, steps in executions.items():
        await store.record_task_executions(_tasks(run_id, *steps))
    return store


async def _analyze(store, mock_task, mock_context) -> dict:
    mock_context.extras["__metrics_store__"] = store
    mock_task.properties = {"days_to_analyze": 7, "min_runs_for_analysis": 1}
    result = await MetricsAnalyzerAction().run(mock_task, mock_context)
    assert result.success is True, result.error
    json.dumps(result.output)  # must be storable as a process property
    return result.output


class TestAnalyzerContinuations:
    async def test_chains_are_gathered(self, seeded_store, mock_task, mock_context):
        ca = (await _analyze(seeded_store, mock_task, mock_context))["continuation_analysis"]

        assert ca["total_continuations"] == 4
        assert ca["total_chains"] == 3
        chain = next(c for c in ca["chains"] if c["leaf_run_id"] == "n2")
        assert chain["length"] == 3
        assert chain["original_workflow"] == "Answer Question"
        assert chain["original_success"] is False
        assert chain["stopped_at"]["last_task"] == "Format"
        assert chain["stopped_at"]["incomplete_tasks"] == ["Format"]
        first, second = chain["continuations"]
        assert first["comment"] == "draw a chart of the numbers"
        assert first["decision"] == "new_workflow"
        assert first["rationale"] == "no charting workflow existed"
        assert second["comment"] is None and second["decision"] is None
        assert chain["final_outcome"] == {
            "workflow_name": "Build Chart",
            "success": True,
            "error": None,
        }

    async def test_continuation_rate_per_workflow(self, seeded_store, mock_task, mock_context):
        stats = {
            s["workflow_name"]: s
            for s in (await _analyze(seeded_store, mock_task, mock_context))["workflow_stats"]
        }

        assert stats["Write Report"]["continued_runs"] == 2
        assert stats["Write Report"]["continuation_rate"] == 0.5
        assert stats["Answer Question"]["continuation_rate"] == 1.0
        assert stats["Build Chart"]["continuation_rate"] == 0.5
        assert stats["Proofread Report"]["continuation_rate"] == 0

    async def test_patterns(self, seeded_store, mock_task, mock_context):
        ca = (await _analyze(seeded_store, mock_task, mock_context))["continuation_analysis"]

        top = ca["frequently_continued"][0]
        assert top["workflow_name"] == "Write Report"
        assert top["continuation_count"] == 2
        assert "also proofread it" in top["comments"]
        assert top["added_steps"] == ["Proofread"]
        assert ca["top_continued"][0] == {"workflow_name": "Write Report", "count": 2}
        assert {"workflow_name": "Write Report", "step": "Proofread", "count": 2} in ca[
            "added_steps"
        ]
        assert [g["continuation_workflow"] for g in ca["capability_gaps"]] == ["Build Chart"]
        assert ca["decision_counts"] == {
            "existing_workflow": 2,
            "new_workflow": 1,
            "unknown": 1,
        }

    async def test_targeted_proposals(self, seeded_store, mock_task, mock_context):
        analysis = await _analyze(seeded_store, mock_task, mock_context)
        proposals = analysis["continuation_analysis"]["proposals"]

        extend = next(p for p in proposals if p["kind"] == "extend")
        assert extend["type"] == "enhance"
        assert extend["target"] == "Write Report"
        assert extend["source"] == "continuation"
        assert "Proofread" in extend["action"]
        assert "also proofread it" in extend["action"]
        promote = next(p for p in proposals if p["kind"] == "promote")
        assert promote["target"] == "Build Chart"
        assert "draw a chart" in promote["action"]
        # Answer Question was continued once: below the default threshold of 2
        assert not any(p["target"] == "Answer Question" for p in proposals)
        assert any("Write Report" in r and "continued" in r for r in analysis["recommendations"])

    async def test_no_continuations(self, mock_task, mock_context):
        analysis = await _analyze(await _plain_store(), mock_task, mock_context)

        ca = analysis["continuation_analysis"]
        assert ca["total_continuations"] == 0
        assert ca["proposals"] == []
        assert all(s["continuation_rate"] == 0 for s in analysis["workflow_stats"])

    async def test_store_failure_degrades(self, mock_task, mock_context):
        store = await _plain_store()
        store.get_continuations_since = AsyncMock(side_effect=RuntimeError("no lineage"))

        analysis = await _analyze(store, mock_task, mock_context)

        assert analysis["total_runs_analyzed"] == 3
        assert analysis["continuation_analysis"]["total_continuations"] == 0


class TestEvaluatorContinuations:
    async def _evaluate(self, analysis, llm_json, mock_task, mock_context, definitions):
        provider = MagicMock()
        provider.complete = AsyncMock(return_value=_response(json.dumps(llm_json)))
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "metrics_analysis": analysis,
            "workflow_definitions": definitions,
        }
        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)
        assert result.success is True
        prompt = provider.complete.call_args.kwargs["messages"][1].content
        return result.output, prompt

    async def test_proposals_merged_when_llm_omits_them(
        self, seeded_store, mock_task, mock_context
    ):
        analysis = await _analyze(seeded_store, mock_task, mock_context)
        llm = {
            "overall_assessment": {"health_score": 80, "summary": "ok", "key_issues": []},
            "improvement_priorities": [
                {"priority": 1, "type": "fix", "target": "Answer Question", "action": "x"}
            ],
            "new_workflow_suggestions": [],
        }

        evaluation, prompt = await self._evaluate(
            analysis, llm, mock_task, mock_context, {"Write Report": _REPORT_YAML}
        )

        assert "Continued Goals" in prompt
        assert "also proofread it" in prompt
        assert "50% continued" in prompt
        priorities = evaluation["improvement_priorities"]
        assert [(p["type"], p["target"]) for p in priorities] == [
            ("enhance", "Write Report"),
            ("create", "Build Chart"),  # promote of a workflow not in the library
            ("fix", "Answer Question"),
        ]
        assert [p["priority"] for p in priorities] == [1, 2, 3]
        assert len(evaluation["continuation_proposals"]) == 2

    async def test_no_duplicate_when_llm_already_proposed(
        self, seeded_store, mock_task, mock_context
    ):
        analysis = await _analyze(seeded_store, mock_task, mock_context)
        llm = {
            "overall_assessment": {"health_score": 80, "summary": "ok", "key_issues": []},
            "improvement_priorities": [
                {"priority": 1, "type": "enhance", "target": "Write Report", "action": "x"}
            ],
            "new_workflow_suggestions": [],
        }
        definitions = {"Write Report": _REPORT_YAML, "Build Chart": _REPORT_YAML}

        evaluation, _ = await self._evaluate(analysis, llm, mock_task, mock_context, definitions)

        targets = [(p["type"], p["target"]) for p in evaluation["improvement_priorities"]]
        assert targets.count(("enhance", "Write Report")) == 1
        assert ("enhance", "Build Chart") in targets


class TestOptimizerContinuations:
    def _setup(self, mock_task, mock_context, tmp_path, responses, priorities, suggestions=()):
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=[_response(r) for r in responses])
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {
                "improvement_priorities": priorities,
                "new_workflow_suggestions": list(suggestions),
                "workflow_evaluations": [],
            },
            "existing_workflows": {"Write Report": _REPORT_YAML},
            "dry_run": False,
            "workflow_library_path": str(tmp_path),
            "max_changes": 1,
        }

    @staticmethod
    def _extend() -> dict:
        return {
            "priority": 1,
            "type": "enhance",
            "kind": "extend",
            "target": "Write Report",
            "action": "Add the steps continuations had to run afterwards: Proofread.",
            "rationale": "continued twice",
            "source": "continuation",
        }

    async def test_continuation_change_made_first(self, mock_task, mock_context, tmp_path):
        extended = _REPORT_YAML.replace("Draft a report", "Draft and proofread a report")
        suggestion = {"name": "Other", "description": "x", "use_case": "y", "rationale": "z"}
        self._setup(mock_task, mock_context, tmp_path, [extended], [self._extend()], [suggestion])

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        out = result.output
        assert out["changes_made"] == [
            {
                "type": "modify",
                "workflow": "Write Report",
                "action": self._extend()["action"],
                "source": "continuation",
            }
        ]
        assert out["continuation_changes"] == [
            {
                "type": "enhance",
                "kind": "extend",
                "workflow": "Write Report",
                "status": "made",
                "reason": "",
            }
        ]
        # max_changes=1 was spent on the continuation proposal
        assert out["skipped"][0]["name"] == "Other"
        assert len(list(tmp_path.glob("*.yaml"))) == 1

    async def test_invalid_continuation_change_is_failed(self, mock_task, mock_context, tmp_path):
        self._setup(mock_task, mock_context, tmp_path, [_BAD_ROUTING_YAML], [self._extend()])

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        out = result.output
        assert out["changes_made"] == []
        assert out["continuation_changes"][0]["status"] == "failed"
        assert out["failed_changes"][0]["workflow"] == "Write Report"
        assert list(tmp_path.iterdir()) == []

    async def test_non_continuation_priorities_not_tracked(self, mock_task, mock_context, tmp_path):
        fix = {"priority": 1, "type": "fix", "target": "Write Report", "action": "x"}
        self._setup(mock_task, mock_context, tmp_path, [_REPORT_YAML], [fix])

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.output["continuation_changes"] == []
        assert "source" not in result.output["changes_made"][0]


async def test_seeded_chains_produce_targeted_change(
    seeded_store, mock_task, mock_context, tmp_path
):
    """Acceptance (#136): seeded chains -> findings -> at least one targeted change."""
    analysis = await _analyze(seeded_store, mock_task, mock_context)
    assert analysis["continuation_analysis"]["total_continuations"] > 0

    eval_provider = MagicMock()
    eval_provider.complete = AsyncMock(
        return_value=_response(json.dumps({"improvement_priorities": []}))
    )
    mock_context.process.properties["__llm_provider__"] = eval_provider
    mock_task.properties = {
        "metrics_analysis": analysis,
        "workflow_definitions": {"Write Report": _REPORT_YAML},
    }
    evaluation = (await WorkflowEvaluatorAction().run(mock_task, mock_context)).output

    opt_provider = MagicMock()
    opt_provider.complete = AsyncMock(return_value=_response(_REPORT_YAML))
    mock_context.process.properties["__llm_provider__"] = opt_provider
    mock_task.properties = {
        "evaluation": evaluation,
        "existing_workflows": {"Write Report": _REPORT_YAML},
        "dry_run": True,
    }
    result = await WorkflowOptimizerAction().run(mock_task, mock_context)

    made = [c for c in result.output["continuation_changes"] if c["status"] == "made"]
    assert {c["workflow"] for c in made} == {"Write Report", "Build Chart"}

"""Tests for the built-in Dream Cycle workflow definition."""

from pathlib import Path

import yaml
from zebra.definitions.loader import load_definition, validate_definition

_DREAM_CYCLE = Path(__file__).parents[1] / "workflows" / "dream_cycle.yaml"


def test_dream_cycle_is_valid():
    assert validate_definition(load_definition(_DREAM_CYCLE)) == []


def test_summary_reports_failed_optimizer_changes():
    """The summary must see rejected changes so it never claims them as fixes (#128)."""
    data = yaml.safe_load(_DREAM_CYCLE.read_text())
    prompt = data["tasks"]["generate_summary"]["properties"]["prompt"]

    assert "{{optimization_results.failed_changes}}" in prompt
    assert "Never describe a failed change as applied" in prompt


def test_summary_reports_continuations():
    """The summary has a Continuations section fed by the analyzer and optimizer (#136)."""
    data = yaml.safe_load(_DREAM_CYCLE.read_text())
    prompt = data["tasks"]["generate_summary"]["properties"]["prompt"]

    assert "### Continuations" in prompt
    assert "{{metrics_analysis.continuation_analysis.total_continuations}}" in prompt
    assert "{{metrics_analysis.continuation_analysis.top_continued}}" in prompt
    assert "{{optimization_results.continuation_changes}}" in prompt


def test_curator_runs_before_workflows_are_loaded():
    """Retired workflows must not reach the evaluator or optimizer (#148)."""
    definition = load_definition(_DREAM_CYCLE)
    routes = {(r.source_task_id, r.dest_task_id) for r in definition.routings}

    assert definition.tasks["curate_workflows"].action == "workflow_curator"
    assert ("analyze_metrics", "curate_workflows") in routes
    assert ("curate_workflows", "load_workflows") in routes
    assert ("analyze_metrics", "load_workflows") not in routes


def test_summary_reports_curation():
    data = yaml.safe_load(_DREAM_CYCLE.read_text())
    prompt = data["tasks"]["generate_summary"]["properties"]["prompt"]

    assert "{{curation.retired}}" in prompt
    assert "{{curation.deferred}}" in prompt


def test_knowledge_review_runs_after_optimisation():
    """The knowledge review (#153) runs after optimisation, before the summary."""
    definition = load_definition(_DREAM_CYCLE)
    routes = {(r.source_task_id, r.dest_task_id) for r in definition.routings}

    assert definition.tasks["review_knowledge"].action == "review_knowledge"
    assert ("golden_gym", "review_knowledge") in routes
    assert ("optimize_workflows", "generate_summary") not in routes


def test_golden_gym_gates_optimizer_modifications():
    """Modifications wait for the golden gym, which runs straight after the optimizer (#171)."""
    definition = load_definition(_DREAM_CYCLE)
    routes = {(r.source_task_id, r.dest_task_id) for r in definition.routings}

    assert definition.tasks["optimize_workflows"].properties["gym_gate"] is True
    gym = definition.tasks["golden_gym"]
    assert gym.action == "run_golden_gym"
    assert gym.properties["candidates"] == "{{optimization_results.pending_gym}}"
    assert ("optimize_workflows", "golden_gym") in routes
    assert ("optimize_workflows", "review_knowledge") not in routes


def test_summary_reports_gym_decisions():
    data = yaml.safe_load(_DREAM_CYCLE.read_text())
    prompt = data["tasks"]["generate_summary"]["properties"]["prompt"]

    assert "{{golden_gym.decisions}}" in prompt


def test_improvement_requests_run_before_summary():
    """Zebra improvement requests (#189) see every finding and feed the summary."""
    definition = load_definition(_DREAM_CYCLE)
    routes = {(r.source_task_id, r.dest_task_id) for r in definition.routings}

    task = definition.tasks["propose_improvements"]
    assert task.action == "propose_zebra_improvements"
    assert task.properties["output_key"] == "improvement_requests"
    assert ("review_knowledge", "propose_improvements") in routes
    assert ("propose_improvements", "generate_summary") in routes
    assert ("review_knowledge", "generate_summary") not in routes


def test_summary_reports_improvement_requests():
    data = yaml.safe_load(_DREAM_CYCLE.read_text())
    prompt = data["tasks"]["generate_summary"]["properties"]["prompt"]

    assert "### Improvements requested" in prompt
    assert "{{improvement_requests.requests}}" in prompt


def test_improvement_request_workflow_is_a_valid_system_workflow():
    path = _DREAM_CYCLE.parent / "zebra_improvement_request.yaml"
    definition = load_definition(path)

    assert validate_definition(definition) == []
    assert definition.name == "Zebra Improvement Request"
    data = yaml.safe_load(path.read_text())
    assert "system" in data["tags"]
    review = definition.tasks["review"]
    assert review.auto is False
    schema = review.properties["schema"]
    assert schema["required"] == ["verdict"]
    assert schema["properties"]["verdict"]["enum"] == ["accepted", "rejected", "duplicate", "later"]


def test_summary_reports_knowledge():
    data = yaml.safe_load(_DREAM_CYCLE.read_text())
    prompt = data["tasks"]["generate_summary"]["properties"]["prompt"]

    assert "### Knowledge" in prompt
    assert "{{knowledge_review.counts}}" in prompt
    assert "{{knowledge_review.examples}}" in prompt

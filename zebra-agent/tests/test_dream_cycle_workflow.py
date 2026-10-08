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

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

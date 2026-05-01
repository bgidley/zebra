"""Tests for the bootstrap_values_taxonomy management command.

The LLM call is mocked; the test focuses on:
- file-not-overwritten-by-default behaviour
- --force overrides the no-overwrite guard
- the validation step rejects malformed LLM output
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError

_VALID_PAYLOAD = {
    "core_values": [
        {"slug": "honesty", "label": "Honesty", "description": "Truthfulness in word and deed."},
    ],
    "ethical_positions": [
        {"slug": "fairness", "label": "Fairness", "description": "Equitable treatment."},
    ],
    "priorities": [
        {"slug": "family", "label": "Family", "description": "Family relationships."},
    ],
    "deal_breakers": [
        {"slug": "no-deception", "label": "No deception", "description": "Never deceive."},
    ],
}


def _mock_provider(payload):
    response = MagicMock(content=json.dumps(payload), model="claude-sonnet")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    return provider


def test_writes_fixture_to_default_path(tmp_path):
    output = tmp_path / "out.yaml"
    out = StringIO()
    with patch(
        "zebra_agent_web.api.management.commands.bootstrap_values_taxonomy.get_provider",
        return_value=_mock_provider(_VALID_PAYLOAD),
    ):
        call_command(
            "bootstrap_values_taxonomy",
            f"--output={output}",
            stdout=out,
        )

    assert output.exists()
    written = yaml.safe_load(output.read_text())
    assert set(written.keys()) == {
        "core_values",
        "ethical_positions",
        "priorities",
        "deal_breakers",
    }
    assert written["core_values"][0]["slug"] == "honesty"
    assert "Wrote 4 tags" in out.getvalue()


def test_refuses_to_overwrite_existing(tmp_path):
    output = tmp_path / "existing.yaml"
    output.write_text("existing: content\n")

    with pytest.raises(CommandError, match="Refusing to overwrite"):
        with patch(
            "zebra_agent_web.api.management.commands.bootstrap_values_taxonomy.get_provider",
            return_value=_mock_provider(_VALID_PAYLOAD),
        ):
            call_command("bootstrap_values_taxonomy", f"--output={output}")

    # Original content untouched.
    assert output.read_text() == "existing: content\n"


def test_force_allows_overwrite(tmp_path):
    output = tmp_path / "existing.yaml"
    output.write_text("existing: content\n")

    with patch(
        "zebra_agent_web.api.management.commands.bootstrap_values_taxonomy.get_provider",
        return_value=_mock_provider(_VALID_PAYLOAD),
    ):
        call_command(
            "bootstrap_values_taxonomy",
            f"--output={output}",
            "--force",
            stdout=StringIO(),
        )

    written = yaml.safe_load(output.read_text())
    assert "core_values" in written


def test_validation_rejects_missing_field(tmp_path):
    output = tmp_path / "out.yaml"
    bad_payload = dict(_VALID_PAYLOAD)
    del bad_payload["deal_breakers"]

    with pytest.raises(CommandError):
        with patch(
            "zebra_agent_web.api.management.commands.bootstrap_values_taxonomy.get_provider",
            return_value=_mock_provider(bad_payload),
        ):
            call_command("bootstrap_values_taxonomy", f"--output={output}")

    assert not output.exists()

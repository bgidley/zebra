"""Tests for WorkflowCuratorAction — dream-cycle retirement of stale workflows (#148)."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import WorkflowStats

from zebra_tasks.agent.curator import WorkflowCuratorAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage


def _yaml(name: str, tags: list[str] | None = None, valid: bool = True) -> str:
    tag_list = ", ".join(f'"{t}"' for t in (tags or []))
    routing = "  - from: a\n    to: b\n" if valid else ""
    return f"""name: "{name}"
description: "Does {name}"
tags: [{tag_list}]
first_task: a
tasks:
  a:
    name: A
    action: llm_call
    properties:
      prompt: hi
  b:
    name: B
    action: llm_call
    properties:
      prompt: bye
routings:
{routing}"""


def _stats(name: str, runs: int, ok: int, days_ago: float | None = 1) -> WorkflowStats:
    last = datetime.now(UTC) - timedelta(days=days_ago) if days_ago is not None else None
    return WorkflowStats(workflow_name=name, total_runs=runs, successful_runs=ok, last_used=last)


def _age(library: WorkflowLibrary, name: str, days: float) -> None:
    """Backdate every file of workflow *name*."""
    ts = time.time() - days * 86400
    for wf in library.list_workflow_files():
        if wf.name == name:
            os.utime(wf.path, (ts, ts))


@pytest.fixture
def library(tmp_path):
    return WorkflowLibrary(tmp_path / "workflows")


@pytest.fixture
def metrics():
    metrics = MagicMock()
    metrics.get_all_stats = AsyncMock(return_value=[])
    return metrics


@pytest.fixture
def context(library, metrics):
    context = MagicMock()
    context.process.properties = {}
    context.extras = {"__workflow_library__": library, "__metrics_store__": metrics}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    return context


def _task(**props):
    task = MagicMock()
    task.properties = {"detect_duplicates": False, **props}
    return task


async def _run(context, **props):
    return await WorkflowCuratorAction().run(_task(**props), context)


def _rules(result) -> dict[str, str]:
    return {d["workflow"]: d["rule"] for d in result.output["retired"]}


async def _active(library) -> list[str]:
    return sorted(w.name for w in await library.list_workflows())


async def test_failing_workflow_is_retired(library, metrics, context):
    library.add_workflow(_yaml("Bad"))
    library.add_workflow(_yaml("Good"))
    metrics.get_all_stats.return_value = [_stats("Bad", 10, 1), _stats("Good", 10, 9)]

    result = await _run(context)

    assert _rules(result) == {"Bad": "failing"}
    assert result.output["retired"][0]["applied"] is True
    assert await _active(library) == ["Good"]
    assert context.process.properties["curation"] == result.output
    json.dumps(result.output)  # report must be JSON-serializable


async def test_failing_needs_enough_runs(library, metrics, context):
    library.add_workflow(_yaml("New"))
    metrics.get_all_stats.return_value = [_stats("New", 2, 0)]

    result = await _run(context)

    assert result.output["retired"] == []


async def test_unused_llm_defined_workflow_is_retired(library, metrics, context):
    library.add_workflow(_yaml("Stale", ["llm-defined"]))
    metrics.get_all_stats.return_value = [_stats("Stale", 3, 3, days_ago=45)]

    result = await _run(context)

    assert _rules(result) == {"Stale": "unused"}


async def test_never_run_llm_defined_uses_file_age(library, context):
    library.add_workflow(_yaml("Old", ["llm-defined"]))
    library.add_workflow(_yaml("Fresh", ["llm-defined"]))
    _age(library, "Old", 40)

    result = await _run(context)

    assert _rules(result) == {"Old": "unused"}


async def test_hand_written_workflow_is_not_retired_for_being_unused(library, metrics, context):
    library.add_workflow(_yaml("Mine", ["web"]))
    _age(library, "Mine", 400)
    metrics.get_all_stats.return_value = [_stats("Mine", 3, 3, days_ago=400)]

    result = await _run(context)

    assert result.output["retired"] == []


async def test_broken_workflow_is_retired(library, context):
    library.add_workflow(_yaml("Truncated", valid=False))

    result = await _run(context)

    [decision] = result.output["retired"]
    assert decision["rule"] == "broken"
    assert "Invalid definition" in decision["reason"]


async def test_system_workflows_are_protected(library, metrics, context):
    library.add_workflow(_yaml("Internal", ["system", "llm-defined"], valid=False))
    library.add_workflow(_yaml("Dream Cycle", valid=False))
    metrics.get_all_stats.return_value = [_stats("Internal", 10, 0)]

    result = await _run(context)

    assert result.output["retired"] == []


async def test_older_same_name_copy_is_retired(library, context):
    library.add_workflow(_yaml("Flow"))
    library.add_workflow(_yaml("Flow"))  # optimizer-style flow_1.yaml
    _age(library, "Flow", 0)
    os.utime(library.library_path / "flow.yaml", (time.time() - 100, time.time() - 100))

    result = await _run(context)

    [decision] = result.output["retired"]
    assert decision == decision | {"rule": "superseded_copy", "file": "flow.yaml"}
    assert [f.path.name for f in library.list_workflow_files()] == ["flow_1.yaml"]


async def test_dry_run_reports_without_retiring(library, metrics, context):
    library.add_workflow(_yaml("Bad"))
    metrics.get_all_stats.return_value = [_stats("Bad", 10, 0)]

    result = await _run(context, dry_run=True)

    assert result.output["dry_run"] is True
    assert result.output["retired"][0]["applied"] is False
    assert await _active(library) == ["Bad"]


async def test_dry_run_from_env(library, metrics, context, monkeypatch):
    monkeypatch.setenv("ZEBRA_CURATOR_DRY_RUN", "true")
    library.add_workflow(_yaml("Bad"))
    metrics.get_all_stats.return_value = [_stats("Bad", 10, 0)]

    result = await _run(context)

    assert result.output["dry_run"] is True
    assert await _active(library) == ["Bad"]


async def test_cap_defers_the_rest(library, metrics, context):
    for i in range(4):
        library.add_workflow(_yaml(f"Bad {i}"))
    metrics.get_all_stats.return_value = [_stats(f"Bad {i}", 10, 0) for i in range(4)]

    result = await _run(context, max_retire=2)

    assert len(result.output["retired"]) == 2
    assert len(result.output["deferred"]) == 2
    assert len(await _active(library)) == 2


async def test_broken_is_applied_before_failing_under_cap(library, metrics, context):
    library.add_workflow(_yaml("Bad"))
    library.add_workflow(_yaml("Broken", valid=False))
    metrics.get_all_stats.return_value = [_stats("Bad", 10, 0)]

    result = await _run(context, max_retire=1)

    assert _rules(result) == {"Broken": "broken"}
    assert result.output["deferred"][0]["workflow"] == "Bad"


async def test_without_library_it_skips(context):
    context.extras = {}

    result = await _run(context)

    assert result.success
    assert result.output["skipped"] == "no library"


async def test_without_metrics_unused_falls_back_to_file_age(library, context):
    context.extras.pop("__metrics_store__")
    library.add_workflow(_yaml("Old", ["llm-defined"]))
    _age(library, "Old", 40)

    result = await _run(context)

    assert _rules(result) == {"Old": "unused"}


# --- duplicate detection --------------------------------------------------


def _llm(pairs: list[dict]) -> MagicMock:
    provider = MagicMock()
    provider.model = "claude-sonnet-4-20250514"
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps({"duplicates": pairs}),
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(input_tokens=100, output_tokens=20),
            model="claude-sonnet-4-20250514",
        )
    )
    return provider


async def _run_dupes(context, provider):
    context.process.properties["__llm_provider_name__"] = "anthropic"
    with patch("zebra_tasks.llm.providers.registry.get_provider", return_value=provider):
        return await _run(context, detect_duplicates=True)


async def test_weaker_llm_defined_duplicate_is_retired(library, metrics, context):
    library.add_workflow(_yaml("Search A", ["llm-defined"]))
    library.add_workflow(_yaml("Search B", ["llm-defined"]))
    metrics.get_all_stats.return_value = [_stats("Search A", 4, 3), _stats("Search B", 4, 1)]
    provider = _llm([{"a": "Search A", "b": "Search B", "reason": "both search the web"}])

    result = await _run_dupes(context, provider)

    [decision] = result.output["retired"]
    assert decision["workflow"] == "Search B"
    assert decision["rule"] == "duplicate"
    assert decision["superseded_by"] == "Search A"
    assert context.process.properties["__total_cost__"] > 0
    [info] = await library.list_retired_workflows()
    assert info.retired["superseded_by"] == "Search A"


async def test_hand_written_duplicate_is_kept(library, metrics, context):
    library.add_workflow(_yaml("Mine"))
    library.add_workflow(_yaml("Generated", ["llm-defined"]))
    metrics.get_all_stats.return_value = [_stats("Mine", 4, 1), _stats("Generated", 4, 4)]
    provider = _llm([{"a": "Mine", "b": "Generated", "reason": "same"}])

    result = await _run_dupes(context, provider)

    assert result.output["retired"] == []


async def test_unknown_names_from_llm_are_ignored(library, context):
    library.add_workflow(_yaml("A", ["llm-defined"]))
    library.add_workflow(_yaml("B", ["llm-defined"]))
    provider = _llm([{"a": "A", "b": "Made Up", "reason": "?"}])

    result = await _run_dupes(context, provider)

    assert result.output["retired"] == []


async def test_duplicate_check_failure_does_not_fail_curation(library, metrics, context):
    library.add_workflow(_yaml("A", ["llm-defined"]))
    library.add_workflow(_yaml("Bad", ["llm-defined"]))
    metrics.get_all_stats.return_value = [_stats("Bad", 10, 0)]
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("API down"))

    result = await _run_dupes(context, provider)

    assert result.success
    assert _rules(result) == {"Bad": "failing"}


async def test_no_llm_call_without_llm_defined_workflows(library, context):
    library.add_workflow(_yaml("Mine"))
    library.add_workflow(_yaml("Yours"))
    provider = _llm([])

    await _run_dupes(context, provider)

    provider.complete.assert_not_called()

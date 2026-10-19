"""Tests for ProposeZebraImprovementsAction — dream-cycle Zebra improvement requests (#189)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult, TaskState
from zebra.definitions.loader import load_definition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary

from zebra_tasks.agent.improvements import (
    REQUEST_WORKFLOW,
    FileImprovementIssueAction,
    ProposeZebraImprovementsAction,
    gather_findings,
    normalize_title,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage

BUILTIN = Path(__file__).parents[2] / "zebra-agent" / "workflows"
PATCH_PROVIDER = "zebra_tasks.agent.improvements.get_llm"

FINDINGS = {
    "evaluation": {
        "overall_assessment": {"health_score": 55, "key_issues": ["Research goals time out"]},
        "improvement_priorities": [{"target": "Web Research", "action": "add retries"}],
    },
    "optimization_results": {
        "failed_changes": [
            {
                "type": "modify",
                "workflow": "Web Research",
                "reason": "unknown action 'http_fetch'",
            }
        ]
    },
    "metrics_analysis": {"continuation_analysis": {"capability_gaps": []}},
}

HTTP_FETCH = {
    "title": "Add an http_fetch task action",
    "area": "task_action",
    "problem": "Workflows cannot fetch a URL; the optimizer's change was rejected.",
    "evidence": "Rejected change to Web Research: unknown action 'http_fetch'",
    "suggested_change": "Add http_fetch to zebra-tasks with a timeout and size cap.",
    "impact": "high",
}


def _response(payload) -> LLMResponse:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        model="test-model",
    )


def _provider(*payloads):
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(p) for p in payloads])
    return provider


@pytest.fixture
def library(tmp_path):
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.copy_builtin_workflows(BUILTIN)
    return lib


@pytest.fixture
def engine(library):
    registry = ActionRegistry()
    registry.register_action("propose_zebra_improvements", ProposeZebraImprovementsAction)
    registry.register_action("file_improvement_issue", FileImprovementIssueAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})


async def _context(engine, properties=None) -> ExecutionContext:
    definition = load_definition(BUILTIN / "dream_cycle.yaml")
    process = await engine.create_process(definition, properties=properties or {})
    return ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=definition.tasks["propose_improvements"],
        extras=engine.extras,
    )


def _task(**props) -> TaskInstance:
    return TaskInstance(
        id="t-improve",
        process_id="p",
        task_definition_id="propose_improvements",
        foe_id="f",
        properties=props,
    )


async def _requests(engine, library) -> list:
    definition = library.get_workflow(REQUEST_WORKFLOW)
    return await engine.store.list_processes(definition_id=definition.id, include_completed=True)


# ---------------------------------------------------------------------------
# Acceptance
# ---------------------------------------------------------------------------


async def test_code_level_gap_becomes_a_request(engine, library):
    context = await _context(engine, {**FINDINGS, "__user_id__": 7})
    provider = _provider({"requests": [HTTP_FETCH]})

    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    out = result.output
    assert out["errors"] == []
    assert [r["title"] for r in out["requests"]] == [HTTP_FETCH["title"]]
    assert context.process.properties["improvement_requests"] == out

    # The LLM saw the rejected change
    prompt = provider.complete.call_args.kwargs["messages"][1].content
    assert "unknown action 'http_fetch'" in prompt

    [process] = await _requests(engine, library)
    assert process.id == out["requests"][0]["process_id"]
    assert process.state == ProcessState.RUNNING
    props = process.properties
    assert props["improvement"]["area"] == "task_action"
    assert props["improvement_title"] == HTTP_FETCH["title"]
    assert props["source_process_id"] == context.process.id
    assert props["__user_id__"] == 7
    assert "#### Suggested change" in props["improvement_markdown"]

    # It waits on the human review task
    tasks = await engine.store.load_tasks_for_process(process.id)
    assert [(t.task_definition_id, t.state) for t in tasks] == [("review", TaskState.READY)]

    # Cost is tracked on the dream cycle
    assert context.process.properties["__total_tokens__"] == 150


async def test_review_completes_the_request(engine, library):
    context = await _context(engine, FINDINGS)
    with patch(PATCH_PROVIDER, return_value=_provider({"requests": [HTTP_FETCH]})):
        await ProposeZebraImprovementsAction().run(_task(), context)

    [process] = await _requests(engine, library)
    [review] = await engine.store.load_tasks_for_process(process.id)
    verdict = {"verdict": "accepted", "issue_url": "https://gitlab.com/gidley/zebra/-/issues/1"}
    await engine.complete_task(review.id, TaskResult.ok(output=verdict))

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_review"]["verdict"] == "accepted"


async def test_nothing_to_analyse_makes_no_llm_call(engine, library):
    context = await _context(engine, {"evaluation": {"overall_assessment": {"key_issues": []}}})
    provider = _provider()

    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    assert result.output == {"requests": [], "skipped": [], "errors": []}
    provider.complete.assert_not_called()
    assert await _requests(engine, library) == []


# ---------------------------------------------------------------------------
# Cap and dedupe
# ---------------------------------------------------------------------------


async def test_cap_limits_requests(engine, library):
    context = await _context(engine, FINDINGS)
    proposals = [{**HTTP_FETCH, "title": f"Improvement {i}"} for i in range(4)]

    with patch(PATCH_PROVIDER, return_value=_provider({"requests": proposals})):
        result = await ProposeZebraImprovementsAction().run(_task(max_requests=2), context)

    assert [r["title"] for r in result.output["requests"]] == ["Improvement 0", "Improvement 1"]
    assert [s["reason"] for s in result.output["skipped"]] == ["over cap", "over cap"]
    assert len(await _requests(engine, library)) == 2


async def test_earlier_request_is_not_repeated(engine, library):
    first = await _context(engine, FINDINGS)
    with patch(PATCH_PROVIDER, return_value=_provider({"requests": [HTTP_FETCH]})):
        await ProposeZebraImprovementsAction().run(_task(), first)

    # Reject it: a later cycle must not raise it again
    [process] = await _requests(engine, library)
    [review] = await engine.store.load_tasks_for_process(process.id)
    await engine.complete_task(review.id, TaskResult.ok(output={"verdict": "rejected"}))

    second = await _context(engine, FINDINGS)
    reworded = {**HTTP_FETCH, "title": "add an HTTP-fetch task action!"}
    provider = _provider({"requests": [reworded]})
    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), second)

    assert result.output["requests"] == []
    assert result.output["skipped"] == [{"title": reworded["title"], "reason": "duplicate"}]
    assert len(await _requests(engine, library)) == 1
    # The earlier title was shown to the LLM
    prompt = provider.complete.call_args.kwargs["messages"][1].content
    assert HTTP_FETCH["title"] in prompt


async def test_request_from_an_older_workflow_version_still_blocks_its_title(engine, library):
    """Definition ids hash name + version; earlier versions must still count (#194)."""
    current = library.get_workflow(REQUEST_WORKFLOW)
    v1 = current.model_copy(update={"id": "zebra-improvement-request-v1", "version": 1})
    await engine.create_process(v1, properties={"improvement_title": HTTP_FETCH["title"]})
    assert v1.id != current.id

    context = await _context(engine, FINDINGS)
    provider = _provider({"requests": [HTTP_FETCH]})
    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.output["requests"] == []
    assert result.output["skipped"] == [{"title": HTTP_FETCH["title"], "reason": "duplicate"}]
    prompt = provider.complete.call_args.kwargs["messages"][1].content
    assert HTTP_FETCH["title"] in prompt


async def test_duplicates_within_one_response(engine, library):
    context = await _context(engine, FINDINGS)
    with patch(PATCH_PROVIDER, return_value=_provider({"requests": [HTTP_FETCH, HTTP_FETCH]})):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert len(result.output["requests"]) == 1
    assert result.output["skipped"][0]["reason"] == "duplicate"


# ---------------------------------------------------------------------------
# Validation and degradation
# ---------------------------------------------------------------------------


async def test_invalid_proposals_are_skipped_and_fields_cleaned(engine, library):
    context = await _context(engine, FINDINGS)
    proposals = [
        {"title": "", "problem": "no title"},
        "not a dict",
        {**HTTP_FETCH, "area": "spaceship", "impact": "huge"},
    ]
    with patch(PATCH_PROVIDER, return_value=_provider({"requests": proposals})):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert len(result.output["requests"]) == 1
    assert result.output["requests"][0]["area"] == "other"
    assert result.output["requests"][0]["impact"] == "medium"
    assert [s["reason"] for s in result.output["skipped"]] == ["invalid", "invalid"]


async def test_unparseable_response_never_fails(engine, library):
    context = await _context(engine, FINDINGS)
    provider = _provider("I think everything is fine.", "Still fine.")
    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    assert result.output["requests"] == []
    assert provider.complete.await_count == 2  # retried once (#195)
    (error,) = result.output["errors"]
    assert error.startswith("unparseable LLM response: invalid JSON")
    assert "(attempts: 2)" in error


async def test_unparseable_response_recovered_on_retry(engine, library):
    context = await _context(engine, FINDINGS)
    provider = _provider("Let me think about this.", {"requests": [HTTP_FETCH]})
    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.output["errors"] == []
    assert len(result.output["requests"]) == 1
    retry_prompt = provider.complete.await_args_list[1].kwargs["messages"][-1].content
    assert "only the JSON object" in retry_prompt


async def test_llm_error_never_fails(engine, library):
    context = await _context(engine, FINDINGS)
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("overloaded"))
    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    assert result.output["errors"] == ["LLM call failed: overloaded"]


async def test_missing_provider_never_fails(engine, library):
    context = await _context(engine, FINDINGS)
    with patch(PATCH_PROVIDER, return_value=None):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    assert result.output["errors"] == ["no LLM provider"]


async def test_start_failure_is_recorded_and_later_requests_still_start(engine, library):
    context = await _context(engine, FINDINGS)
    second = {**HTTP_FETCH, "title": "Expose routing conditions to the UI"}
    real_create = engine.create_process
    calls = 0

    async def flaky_create(definition, properties=None, **kw):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db down")
        return await real_create(definition, properties=properties, **kw)

    engine.create_process = flaky_create
    with patch(PATCH_PROVIDER, return_value=_provider({"requests": [HTTP_FETCH, second]})):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    assert result.output["errors"] == [f"could not start '{HTTP_FETCH['title']}': db down"]
    assert [r["title"] for r in result.output["requests"]] == [second["title"]]


async def test_missing_library_never_fails(engine):
    context = await _context(engine, FINDINGS)
    context.extras = {}
    provider = _provider()
    with patch(PATCH_PROVIDER, return_value=provider):
        result = await ProposeZebraImprovementsAction().run(_task(), context)

    assert result.success
    assert result.output["errors"] == ["workflow library unavailable"]
    provider.complete.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_normalize_title():
    assert normalize_title("Add an HTTP-fetch task action!") == "add an http fetch task action"


def test_gather_findings_tolerates_missing_and_malformed_inputs():
    assert gather_findings({}) == {
        "key_issues": [],
        "improvement_priorities": [],
        "capability_gaps": [],
        "rejected_changes": [],
    }
    found = gather_findings({**FINDINGS, "evaluation": "LLM said no"})
    assert found["key_issues"] == []
    assert len(found["rejected_changes"]) == 1

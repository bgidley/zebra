"""Tests for ReviewKnowledgeAction — dream-cycle knowledge review (F153)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskState
from zebra.definitions.loader import load_definition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext
from zebra.tasks.registry import ActionRegistry
from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import TaskExecution, WorkflowRun
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.knowledge.apply_resolution import ApplyResolutionAction
from zebra_tasks.knowledge.apply_verification_result import ApplyVerificationResultAction
from zebra_tasks.knowledge.review import (
    ReviewKnowledgeAction,
    normalize_key,
    revert_knowledge_changes,
)
from zebra_tasks.knowledge.verify import PickEntriesForVerificationAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage

BUILTIN = Path(__file__).parents[3] / "zebra-agent" / "workflows"
USER = 1
QUIET_USER = 2

COMMUTE_YAML = """name: "Plan Commute"
description: "Plan a commute"
tags: ["travel"]
first_task: ask_details
tasks:
  ask_details:
    name: "Commute Details"
    auto: false
    properties:
      schema:
        type: object
        properties:
          mode: {type: string}
  plan:
    name: "Plan"
    action: llm_call
    properties:
      prompt: plan
routings:
  - from: ask_details
    to: plan
"""


def _entry(entry_id, key, value, source, category="facts", confidence=1.0, **kw):
    entry = KnowledgeEntry.create(
        user_id=kw.pop("user_id", USER),
        category=category,
        key=key,
        value=value,
        source=source,
        confidence=confidence,
        time_sensitive=kw.pop("time_sensitive", False),
    )
    entry.id = entry_id
    if "days_old" in kw:
        entry.last_verified = datetime.now(UTC) - timedelta(days=kw.pop("days_old"))
    return entry


def _response(payload) -> LLMResponse:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        model="test-model",
    )


@pytest.fixture
def library(tmp_path):
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.copy_builtin_workflows(BUILTIN)
    (lib.library_path / "plan_commute.yaml").write_text(COMMUTE_YAML)
    return lib


@pytest.fixture
def knowledge():
    return InMemoryPersonalKnowledgeStore()


@pytest.fixture
def metrics():
    return InMemoryMetricsStore()


@pytest.fixture
def engine(library, knowledge, metrics):
    registry = ActionRegistry()
    registry.register_action("review_knowledge", ReviewKnowledgeAction)
    registry.register_action("pick_entries_for_verification", PickEntriesForVerificationAction)
    registry.register_action("apply_resolution", ApplyResolutionAction)
    registry.register_action("apply_verification_result", ApplyVerificationResultAction)
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={
            "__workflow_library__": library,
            "__knowledge_store__": knowledge,
            "__metrics_store__": metrics,
        },
    )


async def _context(engine) -> ExecutionContext:
    definition = load_definition(BUILTIN / "dream_cycle.yaml")
    process = await engine.create_process(definition, properties={})
    return ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=definition.tasks["review_knowledge"],
        extras=engine.extras,
    )


def _task(**props) -> TaskInstance:
    return TaskInstance(
        id="t-review",
        process_id="p",
        task_definition_id="review_knowledge",
        foe_id="f",
        properties=props,
    )


async def _seed_run(metrics, run_id, goal, user_id=USER, answer=None, **kw):
    run = WorkflowRun(
        id=run_id,
        workflow_name=kw.pop("workflow_name", "Plan Commute"),
        goal=goal,
        started_at=datetime.now(UTC) - timedelta(hours=kw.pop("hours_ago", 1)),
        success=True,
        user_id=user_id,
        **kw,
    )
    await metrics.record_run(run)
    if answer is not None:
        execution = TaskExecution.create(run_id, "ask_details", "Commute Details", 1)
        execution.output = answer
        execution.state = "complete"
        await metrics.record_task_execution(execution)
    return run


def _provider(*payloads):
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(p) for p in payloads])
    return provider


# ---------------------------------------------------------------------------
# Acceptance: one review adds, flags, lowers, and leaves human entries alone
# ---------------------------------------------------------------------------


async def test_review_acceptance(engine, knowledge, metrics):
    seeded = [
        _entry("e-employer", "employer", "Acme", "human"),
        _entry("e-city", "home_city", "Leeds", "human", days_old=400),
        _entry(
            "e-gym",
            "gym_routine",
            "Mondays 7am",
            "agent",
            category="routines",
            confidence=0.8,
            time_sensitive=True,
            days_old=200,
        ),
        _entry("e-editor", "editor", "vim", "agent", category="preferences", confidence=0.7),
        _entry("e-editor2", "text_editor", "vim", "agent", category="preferences", confidence=0.6),
        _entry("e-team", "team", "Platform", "agent", confidence=0.7),
        _entry("e-quiet", "employer", "Initech", "human", user_id=QUIET_USER),
    ]
    for e in seeded:
        await knowledge.add_entry(e)
    human_before = {
        e.id: (e.value, e.confidence, e.last_verified) for e in seeded if e.source == "human"
    }

    await _seed_run(metrics, "r1", "Plan my cycle commute to Globex", answer={"mode": "bike"})
    await _seed_run(
        metrics,
        "r2",
        "Write my Globex intro email",
        workflow_name="Email",
        continuation_comment="I moved to Globex last month",
    )
    await _seed_run(metrics, "r-anon", "orphan run", user_id=None)

    provider = _provider(
        {
            "new": [
                {
                    "category": "routines",
                    "key": "Commute Mode",
                    "value": "cycling",
                    "confidence": 0.95,
                    "evidence": "r1",
                }
            ],
            "update": [
                {"entry_id": "e-employer", "value": "Globex", "evidence": "r2"},
                {"entry_id": "e-team", "value": "Data", "evidence": "r2"},
            ],
            "stale": [
                {"entry_id": "e-gym", "reason": "not mentioned for months"},
                {"entry_id": "e-city", "reason": "old"},
            ],
            "merge": [{"keep_id": "e-editor", "remove_ids": ["e-editor2"], "reason": "dup"}],
            "reinforce": [{"entry_id": "e-editor", "evidence": "r1"}],
        }
    )
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        result = await ReviewKnowledgeAction().run(_task(), context)

    assert result.success
    out = result.output
    # Only USER had runs: one LLM call; the quiet user and the unowned run cost nothing.
    assert provider.complete.await_count == 1
    assert out["users_reviewed"] == 1
    prompt = provider.complete.await_args.kwargs["messages"][1].content
    assert "Initech" not in prompt and "orphan run" not in prompt
    assert '"answer": "{\\"mode\\": \\"bike\\"}"' in prompt  # human-task answer gathered
    assert "I moved to Globex last month" in prompt  # continuation comment gathered

    counts = out["counts"]
    assert counts["added"] == 1
    assert counts["updated"] == 1
    assert counts["stale_flagged"] == 1
    assert counts["merged"] == 1
    assert counts["reinforced"] == 0  # e-editor already touched by the merge
    assert counts["contradictions_proposed"] == 1
    assert counts["verifications_proposed"] == 1

    # New fact: add_knowledge semantics, agent-sourced, below 1.0, normalised key.
    added = await knowledge.find_contradicting_entry(USER, "routines", "commute_mode")
    assert added.value == "cycling" and added.source == "agent"
    assert added.confidence == pytest.approx(0.9)

    # Agent entry updated directly.
    team = await knowledge.get_entry("e-team")
    assert team.value == "Data" and team.confidence == pytest.approx(0.7)

    # Stale time-sensitive agent entry loses confidence (below verification threshold).
    gym = await knowledge.get_entry("e-gym")
    assert gym.confidence == pytest.approx(0.4)
    assert not gym.is_deleted

    # Agent duplicate soft-deleted, keeper intact.
    assert (await knowledge.get_entry("e-editor2")).is_deleted
    assert not (await knowledge.get_entry("e-editor")).is_deleted

    # Human entries untouched.
    for entry_id, snapshot in human_before.items():
        e = await knowledge.get_entry(entry_id)
        assert (e.value, e.confidence, e.last_verified) == snapshot

    # Contradicted human entry → Resolve Knowledge Contradiction waiting on the user.
    proposal = next(c for c in out["changes"] if c["action"] == "contradictions_proposed")
    process = await engine.store.load_process(proposal["process_id"])
    assert process.properties["entry_id"] == "e-employer"
    assert process.properties["proposed_value"] == "Globex"
    assert process.properties["__user_id__"] == USER
    pending = await engine.get_pending_tasks(process.id)
    assert [t.task_definition_id for t in pending] == ["present_contradiction"]

    # Stale human entry → Knowledge Verification for exactly that entry.
    verify = next(c for c in out["changes"] if c["action"] == "verifications_proposed")
    vprocess = await engine.store.load_process(verify["process_id"])
    assert vprocess.properties["review_entry_ids"] == ["e-city"]
    picked = vprocess.properties["entries_to_verify"]["entries"]
    assert [e["id"] for e in picked] == ["e-city"]

    # Audit trail has before/after for every direct change, and nothing for proposals.
    by_action = {c["action"]: c for c in out["changes"]}
    assert by_action["updated"]["before"]["value"] == "Platform"
    assert by_action["updated"]["after"]["value"] == "Data"
    assert by_action["contradictions_proposed"]["after"] is None
    assert out["examples"]["added"] == ["commute_mode: 'cycling'"]

    # Cost tracked on the dream cycle process.
    assert context.process.properties["__total_tokens__"] == 150


async def test_revert_restores_previous_state(engine, knowledge, metrics):
    await knowledge.add_entry(_entry("e-team", "team", "Platform", "agent", confidence=0.7))
    await knowledge.add_entry(_entry("e-unit", "unit", "Ops", "agent", confidence=0.5))
    await knowledge.add_entry(_entry("e-dup", "unit_name", "Ops", "agent", confidence=0.5))
    await _seed_run(metrics, "r1", "team goal")
    provider = _provider(
        {
            "new": [{"category": "facts", "key": "pet", "value": "cat"}],
            "update": [{"entry_id": "e-team", "value": "Data"}],
            "merge": [{"keep_id": "e-unit", "remove_ids": ["e-dup"]}],
        }
    )
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(), context)).output

    reverted = await revert_knowledge_changes(knowledge, out["changes"])
    assert reverted == 3
    team = await knowledge.get_entry("e-team")
    assert (team.value, team.confidence) == ("Platform", 0.7)
    assert not (await knowledge.get_entry("e-dup")).is_deleted
    pet = await knowledge.find_contradicting_entry(USER, "facts", "pet")
    assert pet is None  # the added entry is soft-deleted


# ---------------------------------------------------------------------------
# Cheap paths and graceful degradation
# ---------------------------------------------------------------------------


async def test_no_recent_runs_means_no_llm_call(engine, knowledge, metrics):
    await knowledge.add_entry(_entry("e1", "employer", "Acme", "human"))
    await _seed_run(metrics, "old", "old goal", hours_ago=24 * 30)
    provider = _provider({})
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(lookback_days=7), context)).output
    provider.complete.assert_not_awaited()
    assert out["users_reviewed"] == 0
    assert sum(out["counts"].values()) == 0


async def test_cutoff_is_previous_dream_cycle(engine, knowledge, metrics):
    """Runs before the last completed dream cycle are not reviewed again."""
    context = await _context(engine)
    previous = await engine.create_process(context.process_definition, properties={})
    previous.state = ProcessState.COMPLETE
    previous.created_at = datetime.now(UTC) - timedelta(hours=2)
    await engine.store.save_process(previous)
    await _seed_run(metrics, "before", "seen last time", hours_ago=3)
    provider = _provider({})
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(), context)).output
    provider.complete.assert_not_awaited()
    assert out["cutoff"] == previous.created_at.isoformat()


async def test_missing_stores_degrade(engine):
    context = await _context(engine)
    context.extras = {}
    result = await ReviewKnowledgeAction().run(_task(), context)
    assert result.success
    assert result.output["errors"] == ["metrics or knowledge store unavailable"]
    assert context.process.properties["knowledge_review"]["users_reviewed"] == 0


async def test_unparseable_reply_changes_nothing(engine, knowledge, metrics):
    await knowledge.add_entry(_entry("e1", "team", "Platform", "agent", confidence=0.7))
    await _seed_run(metrics, "r1", "goal")
    provider = _provider("I am not JSON")
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        result = await ReviewKnowledgeAction().run(_task(), context)
    assert result.success
    assert result.output["changes"] == []
    assert result.output["errors"] == [f"user {USER}: LLM reply unusable"]


async def test_invalid_proposals_are_ignored(engine, knowledge, metrics):
    await knowledge.add_entry(_entry("e1", "team", "Platform", "agent", confidence=0.7))
    await knowledge.add_entry(_entry("other", "team", "X", "agent", user_id=QUIET_USER))
    await _seed_run(metrics, "r1", "goal")
    provider = _provider(
        {
            "new": [{"category": "secrets", "key": "pin", "value": "1234"}, "junk"],
            "update": [{"entry_id": "other", "value": "hijack"}, {"entry_id": "nope"}],
            "stale": [{"entry_id": "other"}],
            "merge": [{"keep_id": "e1", "remove_ids": "e1"}],
        }
    )
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(), context)).output
    assert out["changes"] == []
    assert (await knowledge.get_entry("other")).value == "X"


async def test_same_value_new_fact_reinforces_agent_entry(engine, knowledge, metrics):
    await knowledge.add_entry(_entry("e1", "team", "Platform", "agent", confidence=0.6))
    await _seed_run(metrics, "r1", "goal")
    provider = _provider({"new": [{"category": "facts", "key": "team", "value": "Platform"}]})
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(), context)).output
    assert out["counts"]["reinforced"] == 1 and out["counts"]["added"] == 0
    assert (await knowledge.get_entry("e1")).confidence == pytest.approx(0.7)


async def test_pending_contradiction_not_duplicated(engine, knowledge, metrics):
    await knowledge.add_entry(_entry("e-employer", "employer", "Acme", "human"))
    await _seed_run(metrics, "r1", "Globex goal")
    payload = {"update": [{"entry_id": "e-employer", "value": "Globex"}]}
    provider = _provider(payload, payload)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        first = (await ReviewKnowledgeAction().run(_task(), await _context(engine))).output
        second = (await ReviewKnowledgeAction().run(_task(), await _context(engine))).output
    assert first["counts"]["contradictions_proposed"] == 1
    assert second["counts"]["contradictions_proposed"] == 0


async def test_change_cap_per_user(engine, knowledge, metrics):
    await _seed_run(metrics, "r1", "goal")
    provider = _provider(
        {"new": [{"category": "facts", "key": f"k{i}", "value": str(i)} for i in range(5)]}
    )
    context = await _context(engine)
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(max_changes_per_user=2), context)).output
    assert out["counts"]["added"] == 2


def test_normalize_key():
    assert normalize_key("  Commute Mode! ") == "commute_mode"


async def test_resolution_of_proposal_updates_human_entry(engine, knowledge, metrics):
    """The human, not the review, applies the proposed value."""
    await knowledge.add_entry(_entry("e-employer", "employer", "Acme", "human"))
    await _seed_run(metrics, "r1", "Globex goal")
    provider = _provider({"update": [{"entry_id": "e-employer", "value": "Globex"}]})
    with patch("zebra_tasks.knowledge.review._get_provider", return_value=provider):
        out = (await ReviewKnowledgeAction().run(_task(), await _context(engine))).output
    process_id = out["changes"][0]["process_id"]
    (task,) = await engine.get_pending_tasks(process_id)
    from zebra.core.models import TaskResult

    await engine.complete_task(task.id, TaskResult.ok(output={"resolution": "use_new"}))
    assert (await knowledge.get_entry("e-employer")).value == "Globex"
    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE
    assert task.state in (TaskState.READY, TaskState.COMPLETE)

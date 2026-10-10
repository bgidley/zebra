"""Tests for StoreLearnedKnowledgeAction (F152)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore

from zebra_tasks.knowledge.apply_resolution import ApplyResolutionAction
from zebra_tasks.knowledge.store_learned import (
    CONTRADICTION_MARKER,
    StoreLearnedKnowledgeAction,
)

WORKFLOWS_DIR = Path(__file__).parents[3] / "zebra-agent" / "workflows"


class _Library:
    def get_workflow(self, name):
        assert name == "Resolve Knowledge Contradiction"
        return load_definition_from_yaml((WORKFLOWS_DIR / "resolve_contradiction.yaml").read_text())


@pytest.fixture
def knowledge():
    return InMemoryPersonalKnowledgeStore()


@pytest.fixture
def engine(knowledge):
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("apply_resolution", ApplyResolutionAction)
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__knowledge_store__": knowledge, "__workflow_library__": _Library()},
    )


def _context(engine, properties, extras=None):
    context = MagicMock()
    context.engine = engine
    context.store = engine.store
    context.process = MagicMock()
    context.process.id = "main-proc"
    context.process.properties = dict(properties)
    context.extras = engine.extras if extras is None else extras
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    return context


def _task(candidates, **extra):
    task = MagicMock()
    task.id = "store-task"
    task.properties = {"candidates": candidates, **extra}
    return task


def _cand(key="employer", value="Acme", confidence=0.9, category="facts", ts=True):
    return {
        "category": category,
        "key": key,
        "value": value,
        "time_sensitive": ts,
        "confidence": confidence,
    }


async def test_no_user_writes_nothing(engine, knowledge):
    ctx = _context(engine, {})
    result = await StoreLearnedKnowledgeAction().run(_task([_cand()]), ctx)
    assert result.success
    assert result.output["skipped"] == "no_user"
    assert await knowledge.get_entries(1) == []


async def test_no_store_skips(engine):
    ctx = _context(engine, {"__user_id__": 1}, extras={})
    result = await StoreLearnedKnowledgeAction().run(_task([_cand()]), ctx)
    assert result.output["skipped"] == "no_store"


async def test_new_fact_stored_as_agent_with_capped_confidence(engine, knowledge):
    ctx = _context(engine, {"__user_id__": 1})
    result = await StoreLearnedKnowledgeAction().run(_task([_cand()]), ctx)

    [entry] = await knowledge.get_entries(1)
    assert (entry.category, entry.key, entry.value) == ("facts", "employer", "Acme")
    assert entry.source == "agent"
    assert entry.confidence == 0.5
    assert entry.time_sensitive is True
    assert result.output["stored"][0]["entry_id"] == entry.id
    assert ctx.process.properties["learned_knowledge"]["stored"]


async def test_candidates_from_template_and_cap(engine, knowledge):
    cands = [_cand(key=f"k{i}") for i in range(8)]
    ctx = _context(engine, {"__user_id__": 1, "knowledge_candidates": {"candidates": cands}})
    task = _task("{{knowledge_candidates.candidates}}", max_entries=3)
    result = await StoreLearnedKnowledgeAction().run(task, ctx)
    assert len(result.output["stored"]) == 3
    assert len(await knowledge.get_entries(1)) == 3


async def test_same_value_refreshes_without_reaching_full_confidence(engine, knowledge):
    existing = KnowledgeEntry.create(
        user_id=1, category="facts", key="employer", value="Acme", source="agent", confidence=0.3
    )
    await knowledge.add_entry(existing)
    ctx = _context(engine, {"__user_id__": 1})
    result = await StoreLearnedKnowledgeAction().run(_task([_cand()]), ctx)

    [entry] = await knowledge.get_entries(1)
    assert entry.confidence == 0.5
    assert result.output["refreshed"][0]["entry_id"] == existing.id


async def test_conflict_with_human_entry_starts_resolution_and_does_not_overwrite(
    engine, knowledge
):
    human = KnowledgeEntry.create(
        user_id=1, category="facts", key="employer", value="OldCorp", source="human"
    )
    await knowledge.add_entry(human)
    ctx = _context(engine, {"__user_id__": 1})

    result = await StoreLearnedKnowledgeAction().run(_task([_cand(value="NewCorp")]), ctx)

    [entry] = await knowledge.get_entries(1)
    assert entry.value == "OldCorp" and entry.source == "human" and entry.confidence == 1.0

    [conflict] = result.output["contradictions"]
    assert conflict["existing_value"] == "OldCorp"
    assert conflict["existing_source"] == "human"
    process = await engine.store.load_process(conflict["resolution_process_id"])
    assert process.state == ProcessState.RUNNING
    assert process.properties["entry_id"] == human.id
    assert process.properties["proposed_value"] == "NewCorp"
    assert process.properties["__user_id__"] == 1
    assert process.properties[CONTRADICTION_MARKER] == f"{human.id}:NewCorp"
    tasks = await engine.store.load_tasks_for_process(process.id)
    assert [t.task_definition_id for t in tasks if t.state == TaskState.READY] == [
        "present_contradiction"
    ]


async def test_identical_pending_conflict_is_not_duplicated(engine, knowledge):
    await knowledge.add_entry(
        KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="OldCorp")
    )
    ctx = _context(engine, {"__user_id__": 1})
    first = await StoreLearnedKnowledgeAction().run(_task([_cand(value="NewCorp")]), ctx)
    second = await StoreLearnedKnowledgeAction().run(_task([_cand(value="NewCorp")]), ctx)
    pid = first.output["contradictions"][0]["resolution_process_id"]
    assert pid
    assert second.output["contradictions"][0]["resolution_process_id"] == pid
    running = await engine.store.get_processes_by_state(ProcessState.RUNNING)
    assert len(running) == 1


async def test_resolution_use_new_marks_entry_human(engine, knowledge):
    from zebra.core.models import TaskResult

    agent_entry = KnowledgeEntry.create(
        user_id=1, category="facts", key="employer", value="OldCorp", source="agent", confidence=0.5
    )
    await knowledge.add_entry(agent_entry)
    ctx = _context(engine, {"__user_id__": 1})
    result = await StoreLearnedKnowledgeAction().run(_task([_cand(value="NewCorp")]), ctx)
    pid = result.output["contradictions"][0]["resolution_process_id"]

    [pending] = await engine.get_pending_tasks(pid)
    await engine.complete_task(pending.id, TaskResult.ok(output={"resolution": "use_new"}))

    entry = await knowledge.get_entry(agent_entry.id)
    assert entry.value == "NewCorp"
    assert entry.confidence == 1.0
    assert entry.source == "human"


async def test_invalid_candidates_ignored(engine, knowledge):
    ctx = _context(engine, {"__user_id__": 1})
    result = await StoreLearnedKnowledgeAction().run(
        _task([{"category": "nonsense", "key": "a", "value": "b", "confidence": 1}, "junk"]), ctx
    )
    assert result.output["skipped"] == "no_candidates"
    assert await knowledge.get_entries(1) == []


# --- update_agent_entries (F155) -----------------------------------------------------


def _world(value):
    return _cand(key="iran_us_strike_policy", value=value, category="world", confidence=0.7)


async def test_world_category_is_stored(engine, knowledge):
    ctx = _context(engine, {"__user_id__": 1})
    result = await StoreLearnedKnowledgeAction().run(_task([_world("No strikes before vote")]), ctx)

    [entry] = await knowledge.get_entries(1)
    assert entry.category == "world" and entry.source == "agent" and entry.time_sensitive
    assert result.output["stored"][0]["key"] == "iran_us_strike_policy"


async def test_update_agent_entries_updates_developing_story_in_place(engine, knowledge):
    old = KnowledgeEntry.create(
        user_id=1,
        category="world",
        key="iran_us_strike_policy",
        value="Strikes possible",
        source="agent",
        confidence=0.5,
    )
    await knowledge.add_entry(old)
    ctx = _context(engine, {"__user_id__": 1})

    result = await StoreLearnedKnowledgeAction().run(
        _task([_world("No strikes before vote")], update_agent_entries=True), ctx
    )

    [entry] = await knowledge.get_entries(1)
    assert entry.id == old.id
    assert entry.value == "No strikes before vote" and entry.source == "agent"
    assert entry.confidence == 0.5  # capped by max_confidence
    assert result.output["updated"] == [
        {
            "entry_id": old.id,
            "category": "world",
            "key": "iran_us_strike_policy",
            "value": "No strikes before vote",
            "previous_value": "Strikes possible",
        }
    ]
    assert result.output["contradictions"] == []
    assert await engine.store.get_processes_by_state(ProcessState.RUNNING) == []


async def test_update_agent_entries_still_escalates_human_conflicts(engine, knowledge):
    human = KnowledgeEntry.create(
        user_id=1, category="world", key="iran_us_strike_policy", value="Mine", source="human"
    )
    await knowledge.add_entry(human)
    ctx = _context(engine, {"__user_id__": 1})

    result = await StoreLearnedKnowledgeAction().run(
        _task([_world("Agent view")], update_agent_entries=True), ctx
    )

    [entry] = await knowledge.get_entries(1)
    assert entry.value == "Mine"
    assert result.output["updated"] == []
    assert result.output["contradictions"][0]["resolution_process_id"]


async def test_agent_conflict_without_flag_still_starts_resolution(engine, knowledge):
    await knowledge.add_entry(
        KnowledgeEntry.create(
            user_id=1,
            category="world",
            key="iran_us_strike_policy",
            value="Strikes possible",
            source="agent",
        )
    )
    ctx = _context(engine, {"__user_id__": 1})

    result = await StoreLearnedKnowledgeAction().run(_task([_world("No strikes")]), ctx)

    assert result.output["updated"] == []
    assert len(result.output["contradictions"]) == 1

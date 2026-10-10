"""End-to-end run of the Daily News Reading workflow with stubbed fetch and LLM (F155)."""

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.knowledge.store_learned import StoreLearnedKnowledgeAction
from zebra_tasks.web.kagi_news import KagiNewsReadAction

from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore

WORKFLOW = Path(__file__).parents[1] / "workflows" / "daily_news_reading.yaml"

STORIES = [
    {
        "id": f"world:{i}",
        "category": "World",
        "title": f"Story {i}",
        "short_summary": f"Summary {i}",
        "talking_points": [f"Point {i}"],
        "sources": [f"https://example.com/{i}"],
    }
    for i in range(1, 9)
]

LLM_OUTPUTS = {
    "picked": {"picks": [{"id": f"world:{i}", "reason": f"r{i}"} for i in (2, 4, 5, 7, 8)]},
    "digest": "### Story 2\nWhat happened…",
    "world_knowledge": {
        "candidates": [
            {
                "category": "world",
                "key": "story two topic",
                "value": "Story 2 happened on 2026-10-10.",
                "time_sensitive": True,
                "confidence": 0.9,
            },
            {
                "category": "world",
                "key": "ongoing_story",
                "value": "Newer development.",
                "time_sensitive": True,
                "confidence": 0.7,
            },
        ]
    },
}


class StubConsultKnowledge(TaskAction):
    async def run(self, task, context):
        result = {"knowledge": "", "has_knowledge": False}
        context.set_process_property(task.properties["output_key"], result)
        return TaskResult.ok(output=result)


class StubNewsFetch(TaskAction):
    async def run(self, task, context):
        result = {"stories": STORIES, "timestamp": 1, "categories": ["World"]}
        context.set_process_property(task.properties["output_key"], result)
        return TaskResult.ok(output=result)


class StubLLM(TaskAction):
    async def run(self, task, context):
        key = task.properties["output_key"]
        context.set_process_property(key, LLM_OUTPUTS[key])
        return TaskResult.ok(output={"response": LLM_OUTPUTS[key]})


@pytest.fixture
def knowledge():
    return InMemoryPersonalKnowledgeStore()


@pytest.fixture
def engine(knowledge):
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("consult_knowledge", StubConsultKnowledge)
    registry.register_action("kagi_news_fetch", StubNewsFetch)
    registry.register_action("llm_call", StubLLM)
    registry.register_action("kagi_news_read", KagiNewsReadAction)
    registry.register_action("store_learned_knowledge", StoreLearnedKnowledgeAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__knowledge_store__": knowledge})


def test_workflow_metadata():
    definition = load_definition_from_yaml(WORKFLOW.read_text())
    assert definition.name == "Daily News Reading"
    assert definition.properties["result_key"] == "digest"
    assert "system" not in definition.properties.get("tags", [])


async def test_reads_five_stories_and_stores_world_knowledge(engine, knowledge, monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)  # no network: summaries are read
    await knowledge.add_entry(
        KnowledgeEntry.create(
            user_id=1,
            category="world",
            key="ongoing_story",
            value="Earlier development.",
            source="agent",
            confidence=0.5,
        )
    )
    definition = load_definition_from_yaml(WORKFLOW.read_text())
    process = await engine.create_process(
        definition, properties={"goal": "Read today's news", "__user_id__": 1}
    )

    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    props = process.properties

    articles = props["articles"]["articles"]
    assert [a["id"] for a in articles] == ["world:2", "world:4", "world:5", "world:7", "world:8"]
    assert {a["source"] for a in articles} == {"kagi_news"}
    assert props["digest"].startswith("### Story 2")

    learned = props["learned_knowledge"]
    assert [e["key"] for e in learned["stored"]] == ["story_two_topic"]
    assert learned["stored"][0]["confidence"] == 0.7  # capped by max_confidence
    assert [e["key"] for e in learned["updated"]] == ["ongoing_story"]
    assert learned["contradictions"] == []

    entries = {e.key: e for e in await knowledge.get_entries(1)}
    assert entries["ongoing_story"].value == "Newer development."
    assert all(e.category == "world" and e.source == "agent" for e in entries.values())

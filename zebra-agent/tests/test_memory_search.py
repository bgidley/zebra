"""Tests for goal-relevant memory retrieval defaults (#169).

Backends without semantic search rank by keyword overlap with the goal:
``MemoryStore.search_*`` and ``PersonalKnowledgeStore.search_entries``.
"""

from datetime import UTC, datetime, timedelta

from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry
from zebra_agent.storage.interfaces import format_similar_runs_context, keyword_rank
from zebra_agent.storage.memory import InMemoryMemoryStore, InMemoryPersonalKnowledgeStore

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _run(goal: str, age_days: int, success: bool = True) -> WorkflowMemoryEntry:
    return WorkflowMemoryEntry(
        id=goal,
        timestamp=T0 - timedelta(days=age_days),
        workflow_name=f"wf-{goal}",
        goal=goal,
        success=success,
        input_summary="",
        output_summary="",
        effectiveness_notes="",
        tokens_used=0,
    )


def _concept(concept: str, age_days: int, workflow: str = "") -> ConceptualMemoryEntry:
    return ConceptualMemoryEntry(
        id=concept,
        concept=concept,
        recommended_workflows=[{"name": workflow, "fit_notes": ""}] if workflow else [],
        anti_patterns="",
        last_updated=T0 - timedelta(days=age_days),
    )


class TestKeywordRank:
    def test_matches_first_then_input_order(self):
        items = ["cook dinner", "write python code", "review python tests", "walk dog"]
        ranked = keyword_rank(items, str, "python code review", limit=4)
        assert ranked == ["write python code", "review python tests", "cook dinner", "walk dog"]

    def test_empty_query_keeps_order(self):
        assert keyword_rank(["a", "b", "c"], str, "  ", limit=2) == ["a", "b"]

    def test_limit_applies(self):
        assert keyword_rank(["x python", "y python", "z"], str, "python", limit=1) == ["x python"]


class TestInMemoryMemoryStoreSearch:
    async def test_search_workflow_memories_prefers_similar_goals(self):
        store = InMemoryMemoryStore()
        await store.add_workflow_memory(_run("plan a trip to Rome", age_days=10))
        await store.add_workflow_memory(_run("summarise the news", age_days=1))
        await store.add_workflow_memory(_run("plan a weekend trip", age_days=5))

        found = await store.search_workflow_memories("plan a trip to Rome again", limit=3)

        # Rome matches 3 keywords; the weekend trip 2; the news run none (kept last).
        assert [e.goal for e in found] == [
            "plan a trip to Rome",
            "plan a weekend trip",
            "summarise the news",
        ]

    async def test_search_conceptual_memories_uses_concept_and_workflow_names(self):
        store = InMemoryMemoryStore()
        await store.save_conceptual_memory(_concept("Daily news digest", 1))
        await store.save_conceptual_memory(_concept("Travel planning", 9, "Trip Planner"))

        found = await store.search_conceptual_memories("use the trip planner", limit=1)

        assert [e.concept for e in found] == ["Travel planning"]

    async def test_no_match_still_returns_recent(self):
        store = InMemoryMemoryStore()
        await store.save_conceptual_memory(_concept("Older", 9))
        await store.save_conceptual_memory(_concept("Newer", 1))

        found = await store.search_conceptual_memories("quantum chromodynamics", limit=5)

        assert [e.concept for e in found] == ["Newer", "Older"]


class TestInMemoryKnowledgeSearch:
    async def test_search_entries_ranks_by_overlap_and_skips_deleted(self):
        store = InMemoryPersonalKnowledgeStore()

        def entry(key: str, value: str) -> KnowledgeEntry:
            return KnowledgeEntry(
                id=key,
                user_id=7,
                category="preferences",
                key=key,
                value=value,
                source="human",
                confidence=1.0,
                last_verified=T0,
                created_at=T0,
            )

        await store.add_entry(entry("diet", "vegetarian, no mushrooms"))
        await store.add_entry(entry("editor", "uses vim"))
        await store.add_entry(entry("airline", "prefers window seats on flights"))
        await store.soft_delete_entry("editor")

        found = await store.search_entries(7, "book flights to Rome", limit=5)

        assert [e.key for e in found] == ["airline", "diet"]


def test_format_similar_runs_context():
    text = format_similar_runs_context([_run("plan a trip", 0), _run("bad", 1, success=False)])
    assert text.startswith("## Similar Past Goals")
    assert "wf-plan a trip: SUCCESS" in text
    assert "wf-bad: FAILED" in text
    assert format_similar_runs_context([]) == ""

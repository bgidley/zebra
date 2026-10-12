"""E2E: in-database vector memory search on a real Oracle 26ai schema (#169).

CI runs ``manage.py load_embedding_model --strict`` against the per-pipeline
schema before this suite, so the model, columns and triggers are in place.
Skipped on the SQLite fallback.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from django.db import connection

pytestmark = pytest.mark.e2e

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _oracle_only() -> None:
    if connection.vendor != "oracle":
        pytest.skip("vector memory search needs Oracle")


def _embedding_is_set(table: str, row_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE id = %(id)s AND embedding IS NOT NULL",
            {"id": row_id},
        )
        return cursor.fetchone()[0] == 1


def _run(goal: str, workflow: str):  # type: ignore[no-untyped-def]
    from zebra_agent.memory import WorkflowMemoryEntry

    return WorkflowMemoryEntry(
        id=f"e2e-vec-{uuid.uuid4()}",
        timestamp=T0,
        workflow_name=workflow,
        goal=goal,
        success=True,
        input_summary="",
        output_summary="",
        effectiveness_notes="",
        tokens_used=0,
    )


@pytest.fixture
def request_user():
    """Act as a request user: rows are stamped with it and search is scoped to it.

    Exercises the user-id bind — a reserved bind name (UID) once made vector
    search fall back silently.
    """
    from zebra_agent_web.middleware import _current_user_id_var

    user_id = 990_000 + uuid.uuid4().int % 10_000
    token = _current_user_id_var.set(user_id)
    yield user_id
    _current_user_id_var.reset(token)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_memories_are_embedded_and_ranked_by_meaning(request_user, caplog):
    _oracle_only()
    from asgiref.sync import sync_to_async
    from zebra_agent.memory import ConceptualMemoryEntry
    from zebra_agent_web import embeddings
    from zebra_agent_web.memory_store import DjangoMemoryStore

    embeddings.reset_ready_cache()
    assert await sync_to_async(embeddings.vector_search_ready)(), "embedding model not loaded"

    store = DjangoMemoryStore()
    travel = _run("Plan a two-week holiday in France and book the hotels", "Trip Planner")
    code = _run("Find the bug in my Python unit tests", "Code Debugger")
    cooking = _run("Suggest a vegetarian recipe for dinner", "Recipe Finder")
    for entry in (travel, code, cooking):
        await store.add_workflow_memory(entry)
    concept = ConceptualMemoryEntry(
        id=f"e2e-vec-{uuid.uuid4()}",
        concept="Travel and vacation planning",
        recommended_workflows=[{"name": "Trip Planner", "fit_notes": "itineraries"}],
        anti_patterns="",
        last_updated=T0,
    )
    await store.save_conceptual_memory(concept)

    # The trigger embedded every row on insert.
    for entry in (travel, code, cooking):
        assert await sync_to_async(_embedding_is_set)("zebra_workflow_memories", entry.id)
    assert await sync_to_async(_embedding_is_set)("zebra_conceptual_memories", concept.id)

    # No shared keywords with the stored goal: only meaning can rank it first.
    runs = await store.search_workflow_memories("book flights to Paris for my vacation", 3)
    assert runs, "vector search returned nothing"
    assert runs[0].id == travel.id

    concepts = await store.search_conceptual_memories("arrange a trip abroad", 5)
    assert concept.id in [c.id for c in concepts]
    assert "using keyword ranking" not in caplog.text, "vector search fell back"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_knowledge_search_is_semantic_and_skips_deleted(caplog):
    _oracle_only()
    from zebra_agent.knowledge import KnowledgeEntry
    from zebra_agent_web import embeddings
    from zebra_agent_web.knowledge_store import DjangoPersonalKnowledgeStore

    embeddings.reset_ready_cache()
    store = DjangoPersonalKnowledgeStore()
    user_id = 990_000 + uuid.uuid4().int % 10_000

    def entry(key: str, value: str) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            category="preferences",
            key=key,
            value=value,
            source="human",
            confidence=1.0,
            last_verified=T0,
            created_at=T0,
        )

    seat = entry("airline_seat", "always choose a window seat when flying")
    diet = entry("diet", "vegetarian, avoids mushrooms")
    editor = entry("editor", "writes code in vim")
    for e in (seat, diet, editor):
        await store.add_entry(e)
    await store.soft_delete_entry(diet.id)

    found = await store.search_entries(user_id, "book a plane ticket to Rome", limit=3)

    ids = [e.id for e in found]
    assert ids and ids[0] == seat.id
    assert diet.id not in ids
    assert "using keyword ranking" not in caplog.text, "vector search fell back"

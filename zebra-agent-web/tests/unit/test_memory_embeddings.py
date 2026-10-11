"""Unit tests for in-database memory embeddings (#169).

The Oracle path itself runs in the e2e suite against a real schema
(``tests/e2e/test_vector_memory.py``). Here: SQLite fallback behaviour, the
command's non-Oracle skip, and the SQL the embeddings module generates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry
from zebra_agent_web import embeddings
from zebra_agent_web.memory_store import DjangoMemoryStore

T0 = datetime(2026, 10, 1, tzinfo=UTC)


class RecordingCursor:
    """Captures executed SQL; answers COUNT queries with a fixed value and
    trigger-status queries with ``status``."""

    def __init__(self, count: int = 0, status: str = "VALID") -> None:
        self.statements: list[tuple[str, object]] = []
        self._count = count
        self._status = status
        self.rowcount = 3

    def execute(self, sql: str, params: object = None) -> None:
        self.statements.append((sql, params))

    def fetchone(self) -> tuple:
        if self.statements[-1][0].startswith("SELECT status"):
            return (self._status,)
        return (self._count,)

    def sql_starting(self, prefix: str) -> list[str]:
        return [s for s, _ in self.statements if s.startswith(prefix)]


def test_trigger_sql_keeps_plsql_terminator_and_skips_failed_embeddings():
    cursor = RecordingCursor()
    embeddings.install_triggers(cursor, "ZEBRA_EMBED_V1")

    creates = cursor.sql_starting("CREATE OR REPLACE TRIGGER")
    assert len(creates) == len(embeddings.EMBEDDED_TABLES)
    assert not cursor.sql_starting("DROP TRIGGER")
    sql = creates[0]
    assert sql.startswith("CREATE OR REPLACE TRIGGER zebra_wf_mem_embed_trg")
    # No UPDATE OF list: NCLOB columns are not allowed there (ORA-25006).
    assert "BEFORE INSERT OR UPDATE ON zebra_workflow_memories" in sql
    assert 'DBMS_LOB.SUBSTR(:new."GOAL", 1000, 1)' in sql
    assert "VECTOR_EMBEDDING(ZEBRA_EMBED_V1 USING" in sql
    assert "WHEN OTHERS THEN :new.embedding := NULL;" in sql
    # Django's Oracle cursor strips one trailing ";" — the block must survive it.
    assert sql.endswith("END;\n")
    knowledge = creates[2]
    assert ':new."KEY"' in knowledge and ':new."VALUE"' in knowledge


def test_invalid_triggers_are_dropped_so_writes_keep_working():
    # An INVALID trigger would fail every write to its table (ORA-04098).
    cursor = RecordingCursor(count=1, status="INVALID")
    with pytest.raises(RuntimeError, match="embedding triggers invalid"):
        embeddings.install_triggers(cursor, "ZEBRA_EMBED_V1")
    assert cursor.sql_starting("DROP TRIGGER") == [
        f"DROP TRIGGER {t.trigger}" for t in embeddings.EMBEDDED_TABLES
    ]


def test_backfill_touches_only_rows_without_embedding():
    cursor = RecordingCursor()
    counts = embeddings.backfill(cursor)
    assert cursor.statements[0][0] == (
        "UPDATE zebra_workflow_memories SET embedding = NULL WHERE embedding IS NULL"
    )
    assert counts["zebra_knowledge_entries"] == 3


def test_ensure_vector_columns_adds_only_missing():
    missing = RecordingCursor(count=0)
    assert embeddings.ensure_vector_columns(missing) == [
        t.table for t in embeddings.EMBEDDED_TABLES
    ]
    alters = [s for s, _ in missing.statements if s.startswith("ALTER TABLE")]
    assert alters[0] == "ALTER TABLE zebra_workflow_memories ADD (embedding VECTOR(384, FLOAT32))"

    present = RecordingCursor(count=1)
    assert embeddings.ensure_vector_columns(present) == []
    assert not any(s.startswith("ALTER") for s, _ in present.statements)


def test_load_model_binds_credential_and_uri():
    cursor = RecordingCursor()
    embeddings.load_model(cursor, "ZEBRA_EMBED_V1", "https://x/o/m.onnx", "OCI$RESOURCE_PRINCIPAL")
    sql, params = cursor.statements[0]
    assert "DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD" in sql
    assert sql.endswith("END;\n")
    assert params == {
        "name": "ZEBRA_EMBED_V1",
        "cred": "OCI$RESOURCE_PRINCIPAL",
        "uri": "https://x/o/m.onnx",
    }


def test_model_name_must_be_an_identifier():
    with override_settings(ZEBRA_AGENT_SETTINGS={"EMBEDDING_MODEL_NAME": "x; DROP TABLE y"}):
        with pytest.raises(ValueError):
            embeddings.model_name()
    with override_settings(ZEBRA_AGENT_SETTINGS={"EMBEDDING_MODEL_NAME": "zebra_embed_v2"}):
        assert embeddings.model_name() == "ZEBRA_EMBED_V2"


def test_nearest_ids_rejects_unknown_table():
    with pytest.raises(ValueError):
        embeddings.nearest_ids("auth_user", "q", 5)


def test_vector_search_not_ready_on_sqlite():
    embeddings.reset_ready_cache()
    assert embeddings.vector_search_ready() is False


def test_load_embedding_model_skips_on_sqlite():
    out = StringIO()
    call_command("load_embedding_model", "--strict", stdout=out)
    assert "Not an Oracle database" in out.getvalue()


@pytest.mark.django_db(transaction=True)
async def test_django_store_search_falls_back_to_keyword_ranking():
    store = DjangoMemoryStore()
    for goal, age in [("plan a trip to Rome", 10), ("summarise the news", 1)]:
        await store.add_workflow_memory(
            WorkflowMemoryEntry(
                id=goal,
                timestamp=T0 - timedelta(days=age),
                workflow_name="wf",
                goal=goal,
                success=True,
                input_summary="",
                output_summary="",
                effectiveness_notes="",
                tokens_used=0,
            )
        )
    await store.save_conceptual_memory(
        ConceptualMemoryEntry(
            id="c1",
            concept="Travel planning",
            recommended_workflows=[],
            anti_patterns="",
            last_updated=T0,
        )
    )

    runs = await store.search_workflow_memories("trip to Rome", limit=2)
    concepts = await store.search_conceptual_memories("travel", limit=5)

    assert [r.goal for r in runs] == ["plan a trip to Rome", "summarise the news"]
    assert [c.concept for c in concepts] == ["Travel planning"]

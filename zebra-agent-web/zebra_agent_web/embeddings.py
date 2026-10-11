"""In-database vector embeddings for agent memory on Oracle AI Database 26ai (#169).

Embeddings are computed by Oracle itself: an ONNX embedding model is loaded into
the schema from OCI Object Storage (using the database's resource principal), a
``BEFORE INSERT OR UPDATE`` trigger per table fills an ``embedding VECTOR``
column, and retrieval ranks rows with ``VECTOR_DISTANCE``. No Python ML code and
no external embedding API is involved.

The ``embedding`` columns are deliberately *not* declared on the Django models
(Django has no Oracle vector field): Django never reads or writes them, so
export, deletion and compaction are unaffected and every save re-embeds through
the trigger.

Everything here is a no-op on non-Oracle backends; stores fall back to keyword
ranking (``MemoryStore.search_*`` defaults).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

# all-MiniLM-L12-v2 produces 384-dimension float32 vectors.
DIMENSIONS = 384

# How long a negative readiness check is cached before re-checking, so search
# switches on without a restart once the model has been loaded.
_NOT_READY_TTL_SECONDS = 300

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,122}$")


@dataclass(frozen=True)
class EmbeddedTable:
    """A table whose rows carry an embedding of some of their text."""

    table: str
    trigger: str
    text_sql: str  # SQL expression over :new."<COL>" giving the text to embed


# Django's Oracle cursor strips one trailing ";" from every statement, so PL/SQL
# blocks below end with "END;\n" to keep the terminator. Binds use %(name)s.
#
# Django creates columns as quoted upper-case identifiers ("KEY" and "VALUE" are
# Oracle keywords), so column references are quoted the same way. TextField is
# NCLOB on Oracle: the model reads at most ~256 tokens, so the text is cut well
# before the VARCHAR2 limit and TO_CHAR converts it. NCLOB columns cannot appear
# in a trigger's UPDATE OF list (ORA-25006), so the triggers fire on every update.
EMBEDDED_TABLES: tuple[EmbeddedTable, ...] = (
    EmbeddedTable(
        table="zebra_workflow_memories",
        trigger="zebra_wf_mem_embed_trg",
        text_sql='TO_CHAR(DBMS_LOB.SUBSTR(:new."GOAL", 1000, 1))',
    ),
    EmbeddedTable(
        table="zebra_conceptual_memories",
        trigger="zebra_cm_mem_embed_trg",
        text_sql='TO_CHAR(:new."CONCEPT")',
    ),
    EmbeddedTable(
        table="zebra_knowledge_entries",
        trigger="zebra_know_embed_trg",
        text_sql=(
            "TO_CHAR(:new.\"CATEGORY\") || ': ' || TO_CHAR(:new.\"KEY\") || ': ' || "
            'TO_CHAR(DBMS_LOB.SUBSTR(:new."VALUE", 800, 1))'
        ),
    ),
)

_TABLES_BY_NAME = {t.table: t for t in EMBEDDED_TABLES}

_ready_cache: dict[str, float | bool] = {}


def _setting(name: str, default):  # type: ignore[no-untyped-def]
    return getattr(settings, "ZEBRA_AGENT_SETTINGS", {}).get(name, default)


def model_name() -> str:
    """The configured in-database model name, validated as a SQL identifier."""
    name = str(_setting("EMBEDDING_MODEL_NAME", "ZEBRA_EMBED_V1"))
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid EMBEDDING_MODEL_NAME {name!r}")
    return name.upper()


def is_oracle() -> bool:
    return connection.vendor == "oracle"


# =============================================================================
# Schema setup (migration + load_embedding_model command)
# =============================================================================


def _has_column(cursor, table: str, column: str) -> bool:  # type: ignore[no-untyped-def]
    cursor.execute(
        "SELECT COUNT(*) FROM user_tab_columns WHERE table_name = %(t)s AND column_name = %(c)s",
        {"t": table.upper(), "c": column.upper()},
    )
    return cursor.fetchone()[0] > 0


def ensure_vector_columns(cursor) -> list[str]:  # type: ignore[no-untyped-def]
    """Add the ``embedding`` column to each embedded table if missing.

    Returns the tables that were altered.
    """
    added = []
    for t in EMBEDDED_TABLES:
        if not _has_column(cursor, t.table, "embedding"):
            cursor.execute(f"ALTER TABLE {t.table} ADD (embedding VECTOR({DIMENSIONS}, FLOAT32))")
            added.append(t.table)
    return added


def drop_triggers(cursor) -> None:  # type: ignore[no-untyped-def]
    """Drop the embedding triggers that exist."""
    for t in EMBEDDED_TABLES:
        cursor.execute(
            "SELECT COUNT(*) FROM user_triggers WHERE trigger_name = %(n)s",
            {"n": t.trigger.upper()},
        )
        if cursor.fetchone()[0]:
            cursor.execute(f"DROP TRIGGER {t.trigger}")


def drop_vector_columns(cursor) -> None:  # type: ignore[no-untyped-def]
    """Reverse of ``ensure_vector_columns`` (drops triggers first)."""
    drop_triggers(cursor)
    for t in EMBEDDED_TABLES:
        if _has_column(cursor, t.table, "embedding"):
            cursor.execute(f"ALTER TABLE {t.table} DROP COLUMN embedding")


def model_loaded(cursor, name: str) -> bool:  # type: ignore[no-untyped-def]
    cursor.execute(
        "SELECT COUNT(*) FROM user_mining_models WHERE model_name = %(n)s", {"n": name.upper()}
    )
    return cursor.fetchone()[0] > 0


def load_model(cursor, name: str, uri: str, credential: str | None) -> None:  # type: ignore[no-untyped-def]
    """Load the ONNX model from Object Storage into this schema.

    ``credential`` is a DBMS_CLOUD credential name (``OCI$RESOURCE_PRINCIPAL``)
    or None for a pre-authenticated URI. Oracle's prebuilt augmented models
    carry their own metadata, so none is passed.
    """
    cursor.execute(
        "BEGIN DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD("
        "model_name => %(name)s, credential => %(cred)s, uri => %(uri)s); END;\n",
        {"name": name, "cred": credential, "uri": uri},
    )


def smoke_test(cursor, name: str) -> int:  # type: ignore[no-untyped-def]
    """Embed a sample string and return the vector's dimension count."""
    cursor.execute(
        f"SELECT VECTOR_DIMENSION_COUNT(VECTOR_EMBEDDING({name} USING 'hello' AS data)) FROM dual"
    )
    return int(cursor.fetchone()[0])


def install_triggers(cursor, name: str) -> None:  # type: ignore[no-untyped-def]
    """Create (or replace) the per-table embedding triggers.

    A failure to embed never blocks the write: the row is stored with a NULL
    embedding and simply isn't found by vector search until re-embedded.

    A trigger that compiles with errors is still created (INVALID), and an
    invalid trigger makes every write to its table fail (ORA-04098). So the
    triggers are checked after creation; if any is invalid they are all
    dropped and ``RuntimeError`` is raised.
    """
    for t in EMBEDDED_TABLES:
        cursor.execute(
            f"CREATE OR REPLACE TRIGGER {t.trigger}\n"
            f"BEFORE INSERT OR UPDATE ON {t.table}\n"
            "FOR EACH ROW\n"
            "BEGIN\n"
            f"  SELECT VECTOR_EMBEDDING({name} USING {t.text_sql} AS data)\n"
            "    INTO :new.embedding FROM dual;\n"
            "EXCEPTION\n"
            "  WHEN OTHERS THEN :new.embedding := NULL;\n"
            "END;\n"
        )
    invalid = []
    for t in EMBEDDED_TABLES:
        cursor.execute(
            "SELECT status FROM user_objects WHERE object_type = 'TRIGGER' AND object_name = %(n)s",
            {"n": t.trigger.upper()},
        )
        row = cursor.fetchone()
        if row is None or row[0] != "VALID":
            invalid.append(t.trigger)
    if invalid:
        drop_triggers(cursor)
        raise RuntimeError(f"embedding triggers invalid, dropped: {', '.join(invalid)}")


def backfill(cursor) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Embed rows that have no embedding yet.

    Any update fires the row trigger, which computes the embedding (overriding
    the NULL assigned here), so the embedding SQL lives in exactly one place.
    """
    counts = {}
    for t in EMBEDDED_TABLES:
        cursor.execute(f"UPDATE {t.table} SET embedding = NULL WHERE embedding IS NULL")
        counts[t.table] = cursor.rowcount
    return counts


# =============================================================================
# Retrieval
# =============================================================================


def vector_search_ready() -> bool:
    """True when similarity search can run: Oracle, enabled, columns and model present.

    A positive result is cached for the process lifetime; a negative one for
    ``_NOT_READY_TTL_SECONDS``.
    """
    if not is_oracle() or not _setting("MEMORY_VECTOR_SEARCH", True):
        return False
    cached = _ready_cache.get("ready")
    if cached is True:
        return True
    if isinstance(cached, float) and time.monotonic() - cached < _NOT_READY_TTL_SECONDS:
        return False
    try:
        with connection.cursor() as cursor:
            ready = model_loaded(cursor, model_name()) and all(
                _has_column(cursor, t.table, "embedding") for t in EMBEDDED_TABLES
            )
    except Exception as e:  # noqa: BLE001 - readiness must never break retrieval
        logger.warning("Vector search readiness check failed: %s", e)
        ready = False
    if ready:
        _ready_cache["ready"] = True
    else:
        _ready_cache["ready"] = time.monotonic()
        logger.info("Vector memory search not available — using keyword ranking")
    return ready


def reset_ready_cache() -> None:
    """Forget the cached readiness result (after loading the model, and in tests)."""
    _ready_cache.clear()


def nearest_ids(
    table: str,
    query: str,
    limit: int,
    where: str = "",
    params: dict | None = None,
) -> list[str]:
    """Return ids of the rows in ``table`` nearest to ``query``, best first.

    Rows further than ``MEMORY_VECTOR_MAX_DISTANCE`` (cosine) are dropped.

    Args:
        table: One of ``EMBEDDED_TABLES``.
        query: Text to embed and compare against.
        limit: Maximum ids to return.
        where: Extra SQL predicate over the table (alias ``t``), using
            ``%(name)s`` binds supplied in ``params``.
        params: Bind values for ``where``.
    """
    if table not in _TABLES_BY_NAME:
        raise ValueError(f"{table} is not an embedded table")
    max_distance = float(_setting("MEMORY_VECTOR_MAX_DISTANCE", 0.8))
    binds = dict(params or {})
    binds.update({"q": query[:1000], "max_d": max_distance, "lim": int(limit)})
    extra = f" AND ({where})" if where else ""
    sql = (
        f"WITH q AS (SELECT VECTOR_EMBEDDING({model_name()} USING %(q)s AS data) v FROM dual) "
        f"SELECT t.id FROM {table} t, q "
        f"WHERE t.embedding IS NOT NULL{extra} "
        "AND VECTOR_DISTANCE(t.embedding, q.v, COSINE) <= %(max_d)s "
        "ORDER BY VECTOR_DISTANCE(t.embedding, q.v, COSINE) "
        "FETCH FIRST %(lim)s ROWS ONLY"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, binds)
        return [row[0] for row in cursor.fetchall()]

## Context

See `specs/memory-vector-embeddings-design.md` for the full design. Production is Oracle AI Database 26ai on Autonomous Database; dev and unit tests use SQLite.

## Goals / Non-Goals

**Goals:** goal-relevant retrieval for concept memories, past runs and knowledge entries; embeddings computed by the database; no change to workflow definitions or task outputs; SQLite keeps working.

**Non-Goals:** vector indexes (exact scan is negligible at today's few hundred rows), hybrid keyword+vector search, re-embedding on model change (the versioned model name makes it possible later), multilingual models.

## Decisions

- **Model in the database, not in Python.** `VECTOR_EMBEDDING` runs the ONNX model in SQL, so there is no ML dependency, API key or per-call cost.
- **Load from Object Storage with the resource principal.** The 127 MB model never passes through the app container or CI runner, and there is no bearer secret to rotate (rejected: pre-authenticated URL, Python BLOB upload).
- **Triggers, not application code, maintain embeddings.** One place computes them; compaction and feedback updates re-embed automatically. The column is not on the Django models, so export and deletion are unaffected.
- **Fire on every update.** NCLOB columns cannot appear in `UPDATE OF` (ORA-25006); re-embedding a row is cheap.
- **Keyword-overlap fallback.** Interface defaults rank by shared keywords, so SQLite, the in-memory store and a not-yet-loaded model still prefer relevant entries and never return nothing when data exists.

## Risks / Trade-offs

- MiniLM is English-only and reads about 256 tokens: fine for goals and knowledge, which are short.
- The 0.8 cosine-distance cut-off is untuned; configurable via `ZEBRA_MEMORY_VECTOR_MAX_DISTANCE`.
- If the resource principal or IAM policy is missing, search uses keyword ranking (logged); CI's `--strict` load surfaces it.

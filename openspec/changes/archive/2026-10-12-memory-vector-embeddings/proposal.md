## Why

Memory retrieval ignores the goal. `consult_memory` gives the workflow selector the 50 most recently updated concept memories and `consult_knowledge` the 50 most recent knowledge entries, whatever was asked. As memory grows, relevant entries are crowded out by recent but irrelevant ones. Production runs Oracle AI Database 26ai, which can compute embeddings in SQL with an in-database ONNX model, so goal-relevant retrieval needs no external embedding service or separate processing. Issue #169.

## What Changes

- **In-database embedding model.** Oracle's prebuilt augmented all-MiniLM-L12-v2 (384 dimensions) is kept in the private OCI bucket `zebra-models` and loaded into the schema with `DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD`, authenticated by the database's resource principal (no secret). New command `manage.py load_embedding_model [--strict]` loads it (idempotent), smoke-tests it, installs triggers and backfills; the container entrypoint runs it after `migrate`, the e2e job with `--strict`.
- **Embedding columns and triggers.** Migration 0026 adds `embedding VECTOR(384, FLOAT32)` to `zebra_workflow_memories`, `zebra_conceptual_memories` and `zebra_knowledge_entries` (Oracle only; not declared on the Django models). A `BEFORE INSERT OR UPDATE` trigger per table embeds the goal / concept / category-key-value text; a failed embedding stores NULL and never blocks the write.
- **Goal-relevant search.** New store methods `MemoryStore.search_conceptual_memories`, `MemoryStore.search_workflow_memories` and `PersonalKnowledgeStore.search_entries`. Defaults rank by keyword overlap; the Django stores rank by `VECTOR_DISTANCE` (cosine) on Oracle, dropping rows beyond `MEMORY_VECTOR_MAX_DISTANCE`, and fall back to keyword ranking otherwise.
- **Callers.** `consult_memory` uses the 10 nearest concepts plus a new "Similar Past Goals" block (5 nearest past runs; their successful workflows join the shortlist). `consult_knowledge` uses the 20 nearest knowledge entries. Output keys are unchanged.
- **Requirement change.** REQ-DATA-004's "no vector database or embedding infrastructure" becomes "no separate vector database or external embedding service".

## Capabilities

### New Capabilities
- `memory-vector-search`: in-database embeddings and goal-relevant retrieval for memory and knowledge.

### Modified Capabilities
<!-- none -->

## Impact

- zebra-agent: `storage/interfaces.py` (search methods, `keyword_rank`, shared formatters), `storage/memory.py`.
- zebra-agent-web: new `embeddings.py`, migration `0026_memory_embeddings`, command `load_embedding_model`; `memory_store.py`, `knowledge_store.py`, settings.
- zebra-tasks: `consult_memory.py`, `consult_knowledge.py`.
- Ops: `zebra-models` bucket + IAM policy for the ADB resource principal; ADMIN grants for the e2e provisioner; `docker/entrypoint.sh`, `.gitlab-ci.yml`, `scripts/e2e_oracle_schema.py`.

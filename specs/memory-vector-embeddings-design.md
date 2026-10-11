# Memory vector embeddings (#169)

## 1. Goal & scope

Make memory retrieval goal-relevant. Before this, `consult_memory` passed the selector the 50 most recently updated concept memories and `consult_knowledge` the 50 most recent knowledge entries, whatever the goal. Now both retrieve by similarity to the goal, using **Oracle AI Database 26ai's in-database embeddings**: no separate vector DB, no external embedding API, no Python ML code.

Out of scope: vector indexes, hybrid keyword+vector ranking, multilingual models, re-embedding on model upgrade (prepared for by a versioned model name). GitLab: [#169](https://gitlab.com/gidley/zebra/-/work_items/169). OpenSpec: `memory-vector-embeddings` (capability `memory-vector-search`).

## 2. Data model changes

- Migration `0026_memory_embeddings` (Oracle only) adds `embedding VECTOR(384, FLOAT32)` to `zebra_workflow_memories`, `zebra_conceptual_memories`, `zebra_knowledge_entries`. **Not declared on the Django models**: Django never reads or writes it, so export (F9), deletion (F10) and compaction are unchanged.
- Triggers (`zebra_wf_mem_embed_trg`, `zebra_cm_mem_embed_trg`, `zebra_know_embed_trg`), `BEFORE INSERT OR UPDATE`, set `:new.embedding := VECTOR_EMBEDDING(<model> USING <text> AS data)`. Text: workflow memory `goal`; concept `concept`; knowledge `category: key: value`. Long NCLOB text is cut (the model reads ~256 tokens). Embedding errors store NULL and never block the write. NCLOB columns can't be in `UPDATE OF` (ORA-25006), so every update re-embeds.
- Schema object: the ONNX model `ZEBRA_EMBED_V1` (Oracle's prebuilt augmented all-MiniLM-L12-v2, 127 MB, sha256 `3929907d…99ea`).

## 3. API / interface changes

- `MemoryStore.search_conceptual_memories(goal, limit=10)`, `MemoryStore.search_workflow_memories(goal, limit=5)`, `PersonalKnowledgeStore.search_entries(user_id, query, limit=20)`: concrete methods; defaults rank recent entries by keyword overlap (`keyword_rank`, using `search_keywords`), so every backend works.
- `DjangoMemoryStore` / `DjangoPersonalKnowledgeStore` override them: when `embeddings.vector_search_ready()` they call `embeddings.nearest_ids()` (cosine `VECTOR_DISTANCE`, rows beyond `MEMORY_VECTOR_MAX_DISTANCE` dropped, user-scoped, soft-deleted knowledge excluded); on any error they fall back to the defaults.
- Shared formatters in `zebra_agent/storage/interfaces.py`: `format_conceptual_context`, `format_similar_runs_context`.
- `consult_memory`: 10 nearest concepts + "Similar Past Goals" (5 nearest runs; successful runs' workflows join the shortlist). `consult_knowledge`: 20 nearest entries when a goal is given. Output keys unchanged; no YAML change.
- Command `manage.py load_embedding_model [--strict]` (`zebra_agent_web/embeddings.py` holds the SQL).

## 4. Control flow

```
container start: migrate → load_embedding_model → daphne
load_embedding_model: ensure columns → model in user_mining_models? else
  DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD(credential => OCI$RESOURCE_PRINCIPAL, uri => zebra-models object)
  → smoke test (384 dims) → CREATE OR REPLACE triggers → backfill (UPDATE … SET embedding = NULL WHERE embedding IS NULL; trigger computes)
write: Django INSERT/UPDATE → trigger embeds
read: consult_* → store.search_* → vector_search_ready? → nearest_ids (one VECTOR_EMBEDDING of the query in a CTE) : keyword_rank
```

`vector_search_ready()` caches True for the process; False for 5 minutes, so search switches on without a restart once the model loads. Without `--strict`, a load failure logs and exits 0 (deploys are never blocked). CI's e2e job runs it `--strict` against the per-pipeline schema.

**Access**: the database reads the bucket as its own OCI identity (resource principal). One IAM policy:
`Allow any-user to read objects in compartment zebra where ALL {request.principal.type = 'autonomousdatabase', request.principal.id = '<Zebra ADB OCID>', target.bucket.name = 'zebra-models'}`.
ADMIN enabled the resource principal for ADMIN and the prod schema. Per-pipeline e2e schemas need it too, but `ENABLE_RESOURCE_PRINCIPAL(..., grant_option => TRUE)` does **not** let the provisioner call `DBMS_CLOUD_ADMIN` (PLS-00201), and that package is too powerful to grant. Instead ADMIN owns a narrow definer-rights procedure that only accepts `E2E_*` schemas, and `scripts/e2e_oracle_schema.py` calls it:

```sql
CREATE OR REPLACE PROCEDURE ADMIN.ZEBRA_E2E_GRANT_EMBEDDING(p_schema IN VARCHAR2)
  AUTHID DEFINER
AS
  v_schema VARCHAR2(128) := UPPER(p_schema);
BEGIN
  IF NOT REGEXP_LIKE(v_schema, '^E2E_[A-Z0-9_]{1,26}$') THEN
    RAISE_APPLICATION_ERROR(-20001, 'ZEBRA_E2E_GRANT_EMBEDDING: only E2E_* schemas');
  END IF;
  v_schema := DBMS_ASSERT.SCHEMA_NAME(v_schema);  -- must exist
  EXECUTE IMMEDIATE 'GRANT CREATE MINING MODEL TO ' || v_schema;
  EXECUTE IMMEDIATE 'GRANT EXECUTE ON DBMS_CLOUD TO ' || v_schema;
  DBMS_CLOUD_ADMIN.ENABLE_RESOURCE_PRINCIPAL(username => v_schema);
END;
/
GRANT EXECUTE ON ADMIN.ZEBRA_E2E_GRANT_EMBEDDING TO E2E_PROVISIONER;
```

## 5. Configuration (`ZEBRA_AGENT_SETTINGS`)

| Setting | Env var | Default |
|---|---|---|
| `MEMORY_VECTOR_SEARCH` | `ZEBRA_MEMORY_VECTOR_SEARCH` | on (`0` disables) |
| `MEMORY_VECTOR_MAX_DISTANCE` | `ZEBRA_MEMORY_VECTOR_MAX_DISTANCE` | `0.8` (cosine) |
| `EMBEDDING_MODEL_NAME` | `ZEBRA_EMBEDDING_MODEL_NAME` | `ZEBRA_EMBED_V1` |
| `EMBEDDING_MODEL_URI` | `ZEBRA_EMBEDDING_MODEL_URI` | `zebra-models` object URI (not a secret) |
| `EMBEDDING_MODEL_CREDENTIAL` | `ZEBRA_EMBEDDING_MODEL_CREDENTIAL` | `OCI$RESOURCE_PRINCIPAL` |

## 6. Open questions / risks

- The 0.8 distance cut-off is untuned; check prod shortlists and adjust.
- MiniLM is English-only; non-English goals retrieve poorly (keyword fallback is not used when vector search is ready).
- A model upgrade needs: upload `_v2`, set `EMBEDDING_MODEL_NAME`, re-run the command (triggers are replaced), then `UPDATE … SET embedding = NULL` on all rows and drop v1.
- Add an HNSW/IVF vector index if tables grow past ~10k rows.

## 1. Infrastructure

- [x] 1.1 Upload Oracle's prebuilt all-MiniLM-L12-v2 ONNX to private bucket `zebra-models` (sha256 recorded as object metadata)
- [ ] 1.2 IAM policy letting the ADB resource principal read `zebra-models` (manual, tenancy admin)
- [x] 1.3 ADMIN: enable resource principal for ADMIN, prod schema and `E2E_PROVISIONER` (grant option); provisioner grants

## 2. Database

- [x] 2.1 `zebra_agent_web/embeddings.py`: columns, model load, smoke test, triggers, backfill, readiness, `nearest_ids`
- [x] 2.2 Migration 0026: embedding columns (Oracle only)
- [x] 2.3 `load_embedding_model` command; entrypoint runs it after `migrate`; e2e runs it with `--strict`
- [x] 2.4 `scripts/e2e_oracle_schema.py` grants model and resource-principal access to test schemas

## 3. Retrieval

- [x] 3.1 Interface search methods with keyword-overlap defaults; shared formatters
- [x] 3.2 Django memory and knowledge stores: vector search with fallback
- [x] 3.3 `consult_memory` (concepts + similar past goals) and `consult_knowledge`
- [x] 3.4 Settings: `MEMORY_VECTOR_SEARCH`, `MEMORY_VECTOR_MAX_DISTANCE`, `EMBEDDING_MODEL_*`

## 4. Tests and docs

- [x] 4.1 Unit: keyword ranking, in-memory search, consult actions, SQL generation, SQLite fallback
- [x] 4.2 E2E on Oracle: trigger embeds, semantic ranking, knowledge scoping
- [x] 4.3 `specs/memory-vector-embeddings-design.md`, `specs/zebra-as-is.md`, REQ-DATA-004, `specs/zebra-to-be.md`, AGENTS.md files

# memory-vector-search Specification

## Purpose
Goal-relevant retrieval of workflow memories, concept memories and personal knowledge, using Oracle AI Database's in-database embeddings (an ONNX model plus triggers, ranked by `VECTOR_DISTANCE`) and keyword-overlap ranking elsewhere (#169). Design: `specs/memory-vector-embeddings-design.md`.

## Requirements

### Requirement: In-database embedding model
On Oracle, `manage.py load_embedding_model` SHALL ensure the embedding columns exist, load the configured ONNX model from Object Storage with `DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD` when the schema does not already have it, verify it returns 384-dimension vectors, install the embedding triggers and embed rows that have no embedding. It SHALL be idempotent. Without `--strict` a failure SHALL be logged and the command SHALL exit 0; with `--strict` it SHALL exit non-zero. On other databases it SHALL do nothing.

#### Scenario: Already loaded
- **WHEN** the schema already has the model
- **THEN** the command skips the load, reinstalls the triggers and backfills rows without an embedding

#### Scenario: Load fails at startup
- **WHEN** the model cannot be loaded and `--strict` is not given
- **THEN** the command logs a warning and exits 0, and memory search uses keyword ranking

### Requirement: Rows are embedded on write
On Oracle, inserting or updating a workflow memory, conceptual memory or knowledge entry SHALL set its embedding from its goal, concept, or category, key and value respectively. A failure to embed SHALL store a NULL embedding and SHALL NOT fail the write.

#### Scenario: Insert embeds
- **WHEN** a workflow memory is added
- **THEN** its embedding is set

### Requirement: Goal-relevant memory retrieval
`MemoryStore.search_conceptual_memories(goal, limit)`, `MemoryStore.search_workflow_memories(goal, limit)` and `PersonalKnowledgeStore.search_entries(user_id, query, limit)` SHALL return entries most relevant first. When vector search is ready they SHALL rank by cosine distance between stored and query embeddings and drop entries beyond `MEMORY_VECTOR_MAX_DISTANCE`. Otherwise they SHALL rank recent entries by keyword overlap, keeping entries with no overlap after the matches. Knowledge search SHALL exclude soft-deleted entries and be scoped to the user. A vector search error SHALL fall back to keyword ranking.

#### Scenario: Meaning without shared words
- **WHEN** a past goal "Plan a two-week holiday in France" is stored and the query is "book flights to Paris for my vacation"
- **THEN** on Oracle that run ranks first

#### Scenario: SQLite fallback
- **WHEN** the database is SQLite and the goal shares words with one stored goal
- **THEN** that entry ranks first and the rest follow, most recent first

### Requirement: Consult steps use goal-relevant retrieval
`consult_memory` SHALL build its shortlist and context from the 10 conceptual entries most relevant to the goal and SHALL add a "Similar Past Goals" section for the 5 most similar past runs, adding the workflows of successful ones to the shortlist. `consult_knowledge` SHALL use the 20 most relevant knowledge entries when a goal is given, and the most recently verified entries otherwise. Output keys SHALL be unchanged.

#### Scenario: Similar runs shortlisted
- **WHEN** the most similar past run succeeded with workflow "Trip Planner"
- **THEN** "Trip Planner" is in the shortlist and the run appears under "Similar Past Goals"

#### Scenario: No goal for knowledge
- **WHEN** `consult_knowledge` runs without a goal
- **THEN** it returns the most recently verified entries

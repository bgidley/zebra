## Context

The agent currently has a two-tier memory system: **Workflow Memory** (detailed per-run records) and **Conceptual Memory** (compact goal-pattern → workflow index). Both tiers are about *what the agent has done*, not *who the user is*. There is no durable store for user facts, preferences, relationships, or routines. Every goal starts from a blank slate — the agent cannot recall "user prefers Python over Node" or "user works at Acme Corp".

This design introduces a third tier: **Personal Knowledge** — typed, user-scoped entries that survive across sessions and are injected into the planning prompt at the start of each goal.

The existing storage architecture (ABC in `storage/interfaces.py`, concrete backends injected via `engine.extras`) is the established pattern and will be reused exactly.

## Goals / Non-Goals

**Goals:**
- Define `PersonalKnowledgeStore` ABC alongside `MemoryStore` / `MetricsStore`
- Provide `InMemoryPersonalKnowledgeStore` (CLI / tests) and `DjangoPersonalKnowledgeStore` (web)
- Add `consult_knowledge` task action that formats entries as LLM context
- Wire the action into `agent_main_loop.yaml` between `consult_memory` and workflow selection
- Surface knowledge to the selector via a new `knowledge_context` parameter
- Provide `/knowledge/` CRUD web UI for human-managed entries

**Non-Goals:**
- Confidence decay, stale-detection, or lifecycle management (REQ-MEM-005)
- Cross-domain privacy controls for multi-user deployments (REQ-MEM-006)
- Semantic / vector similarity search (category + key filter only)
- Soft-deletes (hard delete keeps the schema minimal)
- Agent-initiated writes to the store (human CRUD only in this iteration)

## Decisions

### 1. Separate ABC, not extending MemoryStore

`PersonalKnowledgeStore` is a new ABC rather than new methods on `MemoryStore`. The two stores have different access patterns (bulk-read by category vs. compacted conceptual index), different lifecycle (knowledge entries persist indefinitely; conceptual memory rebuilds), and different backends may be needed independently.

*Alternative*: Add knowledge methods to `MemoryStore`. Rejected — would force every existing `MemoryStore` implementation to add unrelated methods.

### 2. Dataclass, not Pydantic

`KnowledgeEntry` uses `@dataclass` (same as `WorkflowMemoryEntry` / `ConceptualMemoryEntry`). Pydantic would add validation but the pattern in `memory.py` is dataclasses — consistency matters more than validation here.

### 3. Category enum as plain strings

Categories (`preferences`, `facts`, `relationships`, `routines`, `skills`, `history`) are defined as a module-level tuple of allowed strings (`KNOWLEDGE_CATEGORIES`) rather than a Python `Enum`. The Django model uses a `CharField` with `choices`. This keeps the schema forward-compatible (adding a category is a one-line change) and avoids Enum serialisation edge cases.

### 4. consult_knowledge step placed after consult_memory

Placed between `consult_memory` and `ethics_input_gate` so all context is assembled before ethical and workflow-selection decisions are made. No new routing branches are needed — it always proceeds.

### 5. Selector receives knowledge_context as an additional string parameter

Rather than merging knowledge into `memory_context`, a separate `knowledge_context` field is passed to `WorkflowSelectorAction`. This keeps the two memory tiers auditable in process properties and makes it easy to ablate one without the other.

### 6. CRUD UI uses plain Django views + HTMX partials

Consistent with the existing `/profile/values/`, `/workflows/`, `/runs/` pages — server-rendered HTML with HTMX for inline actions. No new JS dependencies.

## Data Model Changes

**New table**: `zebra_knowledge_entry`

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR2(36) PK | UUID string |
| `user_id` | NUMBER(19) | Indexed; scoped per authenticated user |
| `category` | VARCHAR2(50) | One of `KNOWLEDGE_CATEGORIES` |
| `key` | VARCHAR2(255) | Short identifier (e.g. "preferred_language") |
| `value` | CLOB | The knowledge content |
| `source` | VARCHAR2(50) | `"human"` or `"agent"` |
| `confidence` | FLOAT | 0.0–1.0, default 1.0 |
| `last_verified` | TIMESTAMP | When the entry was last confirmed accurate |
| `created_at` | TIMESTAMP | Auto-set on insert |
| `updated_at` | TIMESTAMP | Auto-updated on save |

Index: `(user_id, category)` for the primary access pattern.

**New migration**: `0NNN_add_knowledge_entry_model.py`

**Interface changes**:
- `storage/interfaces.py`: new `PersonalKnowledgeStore` ABC
- `loop.py`: new optional `knowledge: PersonalKnowledgeStore | None` constructor parameter; inject `__knowledge_store__` into `engine.extras`
- `agent_engine.py`: initialise `DjangoPersonalKnowledgeStore`, inject into engine

## API / Interface Changes

**New task action** (entry-point): `consult_knowledge` → `ConsultKnowledgeAction`

**agent_main_loop.yaml**: new `consult_knowledge` task step between `consult_memory` and `ethics_input_gate`; new routing `consult_knowledge → ethics_input_gate`

**WorkflowSelectorAction**: new optional `knowledge_context` input parameter; appended to planning prompt when non-empty

**New web URLs**:
- `GET  /knowledge/` — list entries (optional `?category=` filter)
- `GET  /knowledge/create/` — create form
- `POST /knowledge/create/` — save new entry
- `GET  /knowledge/<id>/edit/` — edit form
- `POST /knowledge/<id>/edit/` — save update
- `POST /knowledge/<id>/delete/` — delete entry

## Risks / Trade-offs

[Context injection bloat] Injecting all knowledge entries into every planning prompt could inflate token counts for users with many entries → Mitigation: cap at 50 entries in `get_context_for_llm()`; order by `last_verified DESC` so freshest knowledge appears first. Long-term: add semantic filtering (deferred).

[Oracle CLOB size] `value` stored as CLOB; very large entries could slow bulk reads → Mitigation: UI enforces a 2,000-character max on the `value` field.

[Missing `user_id` in standalone CLI] CLI loop passes `user_id=None`; `consult_knowledge` must degrade gracefully → Mitigation: action returns empty context when `user_id` is `None` or store is `None`.

## Migration Plan

1. Run `python manage.py migrate` — creates `zebra_knowledge_entry` table (additive, no data changes)
2. Deploy new code (new views, action, YAML step)
3. No rollback complexity — removing the table is the only rollback step

## Open Questions

- Should the selector's system prompt treat knowledge as higher or lower priority than `memory_context`? Current plan: append after memory context (lower priority). Can be tuned post-launch.
- Should `source` be extended to include specific workflow names? Deferred to REQ-MEM-005.

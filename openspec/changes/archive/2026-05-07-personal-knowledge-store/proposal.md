## Why

The agent has no persistent store for facts, preferences, and knowledge about the user. Every goal starts from scratch — the agent cannot remember that a user prefers dark mode, works at a particular company, or has specific routines. REQ-MEM-004 (F31) calls for a typed, categorised knowledge tier that survives across sessions and informs planning. Closes #31.

## What Changes

- Add a `PersonalKnowledgeStore` abstract interface (new storage tier alongside `MemoryStore` and `MetricsStore`)
- Add `KnowledgeEntry` dataclass with category, key, value, source, confidence, and `last_verified` fields
- Add `InMemoryPersonalKnowledgeStore` for CLI/testing use
- Add `DjangoPersonalKnowledgeStore` backed by a new `KnowledgeEntryModel` ORM model
- Add `consult_knowledge` task action that retrieves relevant entries and formats them for LLM injection
- Integrate `consult_knowledge` into `agent_main_loop.yaml` (runs after `consult_memory`, before workflow selection)
- Update `WorkflowSelectorAction` to accept and use `knowledge_context` in its planning prompt
- Inject `__knowledge_store__` via `engine.extras` in `AgentLoop` and `agent_engine.py`
- Add CRUD web UI: list, create, edit, delete knowledge entries at `/knowledge/`

## Non-goals

- Confidence decay and lifecycle management (REQ-MEM-005 — future)
- Cross-domain privacy controls (REQ-MEM-006 — future)
- Natural language search / semantic similarity (keyword + category filter only for now)
- Soft-deletes (hard delete only in this iteration)

## Capabilities

### New Capabilities

- `personal-knowledge-store`: Typed, user-scoped knowledge entries (category/key/value/confidence) with CRUD web UI and LLM context injection during agent planning

### Modified Capabilities

- *(none — no existing spec-level requirements are changing)*

## Impact

- **zebra-agent**: new `knowledge.py` dataclass, `storage/interfaces.py` extended, new in-memory implementation
- **zebra-tasks**: new `consult_knowledge` entry-point action; `selector.py` accepts `knowledge_context`
- **zebra-agent-web**: new `KnowledgeEntryModel` + migration, new `DjangoPersonalKnowledgeStore`, new views + templates + URL routes
- **agent_main_loop.yaml**: new task step inserted into planning phase
- **No breaking changes** to existing public APIs or workflow definitions

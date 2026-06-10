## Why

Agent memory grows unboundedly: every workflow run writes a full `WorkflowMemoryEntry` and
the conceptual index accumulates entries indefinitely. Without compaction, retrieval context
grows stale and expensive — old runs carry the same weight as recent ones and token budgets
bloat. Closes #11.

## What Changes

- A three-tier retention policy is defined for `WorkflowMemoryEntry`:
  - **Hot** (< 2 weeks): full detail, no change.
  - **Warm** (2 weeks – 2 months): LLM compresses `output_summary` and `effectiveness_notes`
    into a short digest; other fields retained.
  - **Cold** (> 2 months): only metadata retained (`id`, `workflow_name`, `goal` truncated,
    `success`, `timestamp`, `run_id`, `rating`); `output_summary` and `effectiveness_notes`
    cleared.
- A three-tier retention policy is defined for `ConceptualMemoryEntry`:
  - **Hot** (< 2 weeks): unchanged.
  - **Warm** (2 weeks – 2 months): `recommended_workflows` list trimmed to top 3 by
    `use_count`; `anti_patterns` LLM-compressed.
  - **Cold** (> 2 months): `recommended_workflows` trimmed to top 1; `anti_patterns` cleared.
- A `MemoryStore.compact(now)` interface method runs the tiering logic for both entry types.
- A background compaction task runs inside the deployed service on a configurable interval
  (default 6 hours), integrated into the existing daemon loop via `DaemonStarterMiddleware`.
- A `python manage.py compact_memory` management command allows manual triggering.

## Non-goals

- Deleting entries entirely (cold entries are retained as lightweight stubs).
- Compaction of `PersonalKnowledgeStore` (it has its own verification mechanism).
- Per-user compaction scheduling (all users share the same cadence).
- Real-time or per-request compaction.

## Capabilities

### New Capabilities

- `memory-tiers-compaction`: Tiered retention policy and background compaction for
  `WorkflowMemoryEntry` and `ConceptualMemoryEntry`, including the `MemoryStore.compact()`
  interface method, all backend implementations, daemon integration, and management command.

### Modified Capabilities

_(none — no existing spec-level behaviour changes)_

## Impact

- `zebra-agent/zebra_agent/storage/interfaces.py` — new `compact()` abstract method on `MemoryStore`
- `zebra-agent/zebra_agent/storage/memory.py` — `InMemoryMemoryStore.compact()` implementation
- `zebra-agent-web/zebra_agent_web/memory_store.py` — `DjangoMemoryStore.compact()` implementation
- `zebra-agent-web/zebra_agent_web/api/daemon.py` — periodic compaction call in daemon loop
- `zebra-agent-web/zebra_agent_web/api/management/commands/compact_memory.py` — new management command
- `zebra-tasks` — new `compact_memory` task action (entry point) for LLM compression calls
- New tests in `zebra-agent/tests/` and `zebra-tasks/tests/`

## Context

`WorkflowMemoryEntry` and `ConceptualMemoryEntry` accumulate indefinitely. There is no
mechanism to age-out or compress old entries, so retrieval context grows stale and
token-heavy over time. The daemon already runs a routine scheduler (`SchedulerLoop`)
that discovers periodic jobs from `fixtures/routines/*.yaml` — the same mechanism
used for the Dream Cycle.

## Goals / Non-Goals

**Goals:**
- Enforce hot/warm/cold tiering for `WorkflowMemoryEntry` and `ConceptualMemoryEntry`.
- Compress warm entries with an LLM call; strip cold entries to metadata stubs.
- Track tier state to avoid re-processing already-compacted entries.
- Integrate compaction into the deployed service via the existing routine scheduler.
- Provide a `python manage.py compact_memory` command for manual triggering.

**Non-Goals:**
- Hard-deleting entries (cold stubs are retained for audit).
- Per-user cadence or quotas.
- `PersonalKnowledgeStore` (has its own verification path).

## Decisions

### 1. Routine scheduler, not daemon-loop code

The daemon loop uses `SchedulerLoop` + `fixtures/routines/*.yaml`. Adding a new
`compact_memory.yaml` routine (schedule: `0 */6 * * *`) keeps the pattern consistent
with `dream_cycle.yaml` and requires zero Python changes to the daemon. The routine
references a new `"Compact Memory"` workflow (single task: `compact_memory` action).

Alternative: call `memory_store.compact()` directly inside `_goal_queue_tick_fn` on
every N-th tick. Rejected — pollutes the tick function and makes compaction harder to
observe, skip, or tune independently.

### 2. Add `tier` field to both entry types

Track the current tier (`"hot"`, `"warm"`, `"cold"`) on each entry so the compaction
action can skip already-processed entries. Without this, every compaction run would
re-compress warm entries or re-strip cold ones.

- `WorkflowMemoryEntry`: add `tier: str = "hot"` field.
- `ConceptualMemoryEntry`: add `tier: str = "hot"` field.
- DB: two new `VARCHAR(10)` columns, default `'hot'`. Migrations required.
- `MemoryStore`: add `update_workflow_memory_tier(entry_id, tier, **compressed_fields)`
  and `update_conceptual_memory_tier(entry_id, tier, **compressed_fields)` interface
  methods so backends can update in-place without full replace.

### 3. LLM compression in a `CompactMemoryAction` task action

Follows the existing task action pattern (entry-point in `pyproject.toml`, reads
`__memory_store__` from `context.extras`). The action:
1. Fetches all entries from the memory store.
2. Classifies each into hot/warm/cold by comparing `timestamp` to `now`.
3. For newly-warm `WorkflowMemoryEntry`: calls LLM to compress `output_summary` +
   `effectiveness_notes` into a single digest (≤150 tokens), then updates tier.
4. For newly-cold `WorkflowMemoryEntry`: clears `output_summary` and
   `effectiveness_notes`, sets tier.
5. For newly-warm `ConceptualMemoryEntry`: trims `recommended_workflows` to top 3 by
   `use_count`; calls LLM to compress `anti_patterns`; updates tier.
6. For newly-cold `ConceptualMemoryEntry`: trims to top 1; clears `anti_patterns`;
   updates tier.
7. Degrades gracefully (logs warning, returns success) if memory store is absent.

LLM calls are batched per entry — no parallelism needed at this scale.

### 4. `MemoryStore.get_entries_for_compaction()` interface method

Rather than fetching all entries and filtering in Python, backends can return only
entries whose tier is stale for their age. This keeps the action portable and lets
Oracle/SQLite do the filtering efficiently.

Signature: `get_entries_for_compaction(now: datetime) -> CompactionBatch` where
`CompactionBatch` is a simple dataclass with `warm_workflow`, `cold_workflow`,
`warm_conceptual`, `cold_conceptual` lists.

## Data Model Changes

| Model | Change |
|-------|--------|
| `WorkflowMemoryModel` | Add `tier VARCHAR(10) DEFAULT 'hot'` |
| `ConceptualMemoryModel` | Add `tier VARCHAR(10) DEFAULT 'hot'` |
| `WorkflowMemoryEntry` | Add `tier: str = "hot"` field |
| `ConceptualMemoryEntry` | Add `tier: str = "hot"` field |

New `MemoryStore` interface methods:
- `get_entries_for_compaction(now: datetime) -> CompactionBatch`
- `apply_compaction(batch: CompactionResult) -> None`

## API / Interface Changes

- New entry point: `compact_memory = "zebra_tasks.agent.compact_memory:CompactMemoryAction"`
- New workflow: `zebra-agent/workflows/compact_memory.yaml` (`"Compact Memory"`)
- New routine: `zebra-agent-web/fixtures/routines/compact_memory.yaml` (every 6 hours)
- New management command: `zebra-agent-web/zebra_agent_web/api/management/commands/compact_memory.py`
- New setting: `MEMORY_COMPACTION_INTERVAL_HOURS` (default 6) in `ZEBRA_AGENT_SETTINGS`

## Risks / Trade-offs

[LLM cost per compaction run] → Warm compression uses one LLM call per newly-warm entry.
At normal usage volumes this is negligible; set `budget_aware: false` on the routine so
it runs regardless of daily budget state. Log token usage.

[Re-running compaction on already-compacted entries] → Mitigated by the `tier` field.
The `get_entries_for_compaction` query only returns entries whose current tier is
staler than their age-based tier.

[DB migration on deployed instance] → Standard Django migration; columns have safe
defaults so the migration is non-breaking.

## Migration Plan

1. Run `python manage.py migrate` — adds `tier` columns to both tables (safe default `'hot'`).
2. Deploy new code (daemon picks up new routine on next start).
3. First compaction run (within 6 hours) classifies all existing entries.

Rollback: remove the routine YAML, revert migration.

## Open Questions

None.

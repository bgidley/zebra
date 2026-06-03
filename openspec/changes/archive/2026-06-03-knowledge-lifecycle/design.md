## Context

The personal knowledge store (F31) persists typed, user-scoped facts but has no lifecycle: entries never decay, are never challenged for staleness, and contradictions silently overwrite existing values. This design adds confidence decay, periodic human verification, contradiction detection with dilemma escalation, and soft-delete to close REQ-MEM-005.

The existing `KnowledgeEntry` dataclass and `PersonalKnowledgeStore` ABC are extended, not replaced.

## Goals / Non-Goals

**Goals:**
- Confidence decays over time for time-sensitive entries (configurable half-life per category)
- Scheduled weekly verification workflow surfaces low-confidence entries to the user
- Writing a contradicting value raises a detectable signal; the caller routes to a dilemma workflow
- Deletes are soft (audit trail preserved); active queries exclude deleted entries

**Non-Goals:**
- Automatic merging of contradicting entries without human confirmation
- Cross-domain knowledge access (REQ-MEM-006)
- Multi-user privacy boundaries

## Decisions

### 1. Lifecycle fields added directly to `KnowledgeEntry`

Add `deleted_at: datetime | None = None` and `time_sensitive: bool = False` to the existing dataclass rather than a separate lifecycle table.

*Why*: Avoids a join on every read. The existing `confidence` field is already the core lifecycle signal; `deleted_at` and `time_sensitive` are direct properties of an entry, not metadata about it.

### 2. Half-life per category stored as a module-level constant

```python
CATEGORY_DECAY_HALF_LIFE_DAYS: dict[str, int | None] = {
    "facts": 365, "preferences": 180, "relationships": 90,
    "routines": 60, "skills": 730, "history": None,
}
```

Only entries where `time_sensitive=True` are decayed. `None` means no decay.

*Why*: Simple, inspectable, zero runtime config overhead. A DB-backed config table would be over-engineering for a single-user agent.

### 3. Contradiction detection in store; raised as `ContradictionError`

`PersonalKnowledgeStore.add_entry` gains a companion method `find_contradicting_entry(user_id, category, key) -> KnowledgeEntry | None`. Before calling `add_entry`, the caller (task action) checks for a contradiction.

A new `add_knowledge` task action encapsulates the check-then-store pattern:
1. Call `find_contradicting_entry`
2. If conflict found → return `TaskResult.ok(next_route="contradiction", output={existing: ..., proposed: ...})`
3. If no conflict → call `add_entry` and return `TaskResult.ok(next_route="stored")`

*Why*: Keeping detection in the task action (not the store) preserves the store as a dumb persistence layer and lets the routing be expressed in YAML. The store method is a query, not a policy decision.

### 4. Contradiction resolution via dilemma sub-workflow

A `resolve_contradiction.yaml` workflow presents the existing and proposed values to the user as a human task, then either keeps the existing value, accepts the new one, or stores both.

*Why*: Consistent with Zebra's workflow-first philosophy — complex multi-step human interactions belong in YAML workflows, not in task action code.

### 5. Scheduled routines via `zebra.schedules` entry points

Two new routines registered under `zebra.schedules`:
- `knowledge_decay_daily` → `decay_confidence.yaml` (runs daily at midnight)
- `knowledge_verification_weekly` → `knowledge_verification.yaml` (runs weekly on Mondays)

*Why*: Consistent with the polling scheduler design (zebra-to-be §7). No new scheduling mechanism needed.

## Risks / Trade-offs

- **Decay is irreversible within a session** — confidence is updated in place; there's no rollback if decay runs incorrectly. Mitigation: decay is bounded (never below 0.1 to avoid permanently burying valid entries).
- **Contradiction detection is key-exact** — two entries with semantically equivalent but differently-worded keys won't be caught. Mitigation: out-of-scope for this issue; document the limitation.
- **Soft delete increases query complexity** — every `get_entries` query must filter `deleted_at IS NULL`. Mitigation: both implementations apply the filter at the store level, transparent to callers.

## Migration Plan

1. Add `deleted_at` (nullable datetime) and `time_sensitive` (bool, default False) columns via Django migration.
2. All existing rows get `deleted_at = NULL` and `time_sensitive = False` — no data migration needed.
3. `get_entries` is backwards-compatible: the default `include_deleted=False` matches prior behaviour.

## Open Questions

- Should the weekly verification email / notification the user or surface via the web UI only? (Deferred to notification system REQ-UI-004.)
- Should `add_knowledge` be in `zebra-tasks` or `zebra-agent`? Recommend `zebra-tasks` for consistency with `consult_knowledge`.

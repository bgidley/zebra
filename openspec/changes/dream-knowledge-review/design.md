## Context

Knowledge entries (`KnowledgeEntry`: category, key, value, source human|agent, confidence, last_verified, time_sensitive, soft delete) live in a `PersonalKnowledgeStore` (`__knowledge_store__`). Runs live in the `MetricsStore`; the Django `WorkflowRunModel` already has a `user_id` column but the `WorkflowRun` dataclass did not expose it. *Resolve Knowledge Contradiction* and *Knowledge Verification* are existing human-task workflows. The dream cycle runs without a request user.

## Goals / Non-Goals

**Goals:** keep knowledge current from recent runs, never auto-edit human entries, make every change auditable and undoable, cost nothing for idle users.

**Non-Goals:** no new tables or migration, no UI for the audit trail, no per-run extraction (that is #152), no change to the decay / weekly verification schedule.

## Decisions

- **Separate dream-cycle step**, after `optimize_workflows`. Workflow analysis and knowledge review are independent; the step never fails the cycle (errors go to `errors`).
- **Window** = start of the previous COMPLETE process of the same Dream Cycle definition (found via `StateStore.list_processes(definition_id)`), else `lookback_days` (7). A version bump changes the definition id, so the first v6 cycle uses the fallback.
- **Per-user grouping** via new `WorkflowRun.user_id`. `assess_and_record` sets it from `__user_id__`; the Django store prefers it over the request user when recording and maps it when reading. Runs without an owner are ignored, and users without runs are never visited, so they cost no LLM call.
- **Human answers** = outputs of task executions whose task id is an `auto: false` task in the run's workflow definition (via `WorkflowLibrary`).
- **One LLM call per user**, JSON reply. Invalid ids, other users' ids, unknown categories and malformed items are dropped. Each entry is acted on once per review; order: update, merge, stale, reinforce, new. At most `max_changes_per_user` (10) non-reinforce actions.
- **Apply rules**
  - update: agent → set value, confidence 0.7, `last_verified` now; human → start contradiction workflow (props `entry_id`, `existing_value`, `proposed_value`, `category`, `key`, `__user_id__`); same value → reinforce.
  - stale: agent → confidence `max(0.1, min(c × 0.5, 0.5))` (below the 0.6 verification threshold); human → verification proposal.
  - merge: agent duplicates soft-deleted (reversible); human duplicates → verification proposal; the keeper is untouched.
  - reinforce: agent → `last_verified` now, confidence +0.1 capped at 0.9; human → untouched.
  - new: `find_contradicting_entry` first (add_knowledge semantics); none → add `source="agent"`, confidence clamped to [0.1, 0.9], key normalised to snake_case; clash → treated as update.
- **Proposals are processes** created and started by the action (they park on their human task), owned by the user via `__user_id__`. An unfinished proposal for the same entry/value (contradiction) or entry (verification) is not duplicated. Verification gets `review_entry_ids`; `pick_entries_for_verification` selects exactly those active, owned entries.
- **Audit** = `knowledge_review.changes` on the dream-cycle process: action, user, entry, source, before/after snapshot (value, confidence, last_verified, deleted_at), reason, time, and `process_id` for proposals. `revert_knowledge_changes(store, changes)` restores `before` (or soft-deletes added entries).

## Risks / Trade-offs

- LLM may propose spurious facts → agent confidence < 1.0, change cap, weekly verification, revert helper.
- Audit lives in process properties rather than a dedicated table; enough for audit/undo now, a store-level history could follow if needed.
- If the dream cycle is triggered by an authenticated API user, the Django metrics store scopes `get_runs_since` to that user, so only their knowledge is reviewed (same as the metrics analysis).
- Overlap with #152: both write agent-sourced entries through the same semantics; the review sees #152's entries as ordinary agent entries.

## Why

The dream cycle improves workflows but never looks at the personal knowledge store, so stored facts go stale and facts that recur across runs are never picked up unless a per-run step catches them. GitLab issue #153 (related: #152 per-run learning, #32 lifecycle, #136 dream continuations).

## What Changes

- New `review_knowledge` task action (`zebra_tasks/knowledge/review.py`), run in `dream_cycle.yaml` v6 after `optimize_workflows`, before the summary.
- Per user with runs since the last dream cycle: gather active entries and recent runs (goal, outcome, rating, continuation comment, answers to human tasks), one LLM call proposes `new` / `update` / `stale` / `merge` / `reinforce`, and the action applies them:
  - agent-sourced entries change directly (value, confidence, `last_verified`, soft delete of duplicates);
  - new facts follow `add_knowledge` semantics (`source="agent"`, confidence < 1.0);
  - `source="human"` entries are never written: conflicts start *Resolve Knowledge Contradiction*, stale or duplicate human entries start *Knowledge Verification* for exactly those entries;
  - stale entries lose confidence, never deleted.
- Every change and proposal goes into an audit list with before/after state; `revert_knowledge_changes()` undoes the direct changes.
- Summary gets a "Knowledge" section (counts and examples).
- `WorkflowRun.user_id` (new optional field) so runs can be grouped per user; `assess_and_record` sets it from `__user_id__`, the Django metrics store reads and writes it.
- `pick_entries_for_verification` honours a `review_entry_ids` process property.

## Capabilities

### New Capabilities
- `dream-knowledge-review`: dream-cycle review of personal knowledge against recent runs.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks/zebra_tasks/knowledge/review.py` (new), `knowledge/verify.py`, `agent/assess_and_record.py`, `zebra-tasks/pyproject.toml` entry point
- `zebra-agent/zebra_agent/metrics.py` (`WorkflowRun.user_id`), `zebra-agent/workflows/dream_cycle.yaml` v6
- `zebra-agent-web/zebra_agent_web/metrics_store.py` (map existing `user_id` column; no migration)
- Tests in `zebra-tasks/tests/knowledge/`, `zebra-agent/tests/test_dream_cycle_workflow.py`, `zebra-agent-web/tests/unit/test_metrics_search_runs.py`

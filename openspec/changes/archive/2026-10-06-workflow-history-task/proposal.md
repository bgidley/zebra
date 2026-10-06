# Proposal

Closes #138

## Why

Zebra records every goal run (`WorkflowRun` in `MetricsStore`), but no workflow can read that
history. Goals like "what did I ask you about pensions last week?" or "have we tried this before —
how did it go?" can't be answered, and the selector plans without knowing what happened on similar
past goals. The store can't filter by end date or by text either.

## What Changes

- New `MetricsStore.search_runs(...)` query with optional `since` / `until` / `text` /
  `workflow_name` / `success` / `limit` filters. It is implemented in both the in-memory store and
  the Django/Oracle store, and the Django store keeps its existing per-user scoping.
- New task action **`get_workflow_history`**: a deterministic fetch that accepts ISO or relative
  dates (`-7d`, `24h`) and returns compact runs plus a size-bounded `history_context` string ready
  for an LLM prompt. It can be reused in any workflow.
- New task action **`assess_history_need`**: decides whether a goal needs history. A cheap keyword
  pre-check runs first, then a Haiku call only when cues are present. It routes `needs_history` or
  `no_history` and extracts the filters (date range, search text).
- `agent_main_loop.yaml` (version bump): adds `consult_knowledge → assess_history_need →
  [get_workflow_history] → ethics_input_gate`. `workflow_selector` receives `history_context`, and
  `execute_goal_workflow` appends it to the child's goal, the same way previous-run context is
  passed today (F116).

## Capabilities

### New Capabilities
- `workflow-history`: querying past workflow runs by time window and text, the history-need
  decision, and passing history into downstream planning and execution.

### Modified Capabilities
- (none)

## Non-goals

- Semantic or vector search over history. v1 matches text only.
- Task-level history (`__task_output_*` from the process store). v1 returns run-level records only.
- Orphaned processes with no `WorkflowRunModel`.
- New UI or REST endpoints.

## Impact

- `zebra-agent`: `storage/interfaces.py`, `storage/metrics.py`, `workflows/agent_main_loop.yaml`.
- `zebra-agent-web`: `metrics_store.py`. No migration; it uses the existing indexed `started_at`.
- `zebra-tasks`: two new actions in `agent/`, entry points in `pyproject.toml`, `selector.py`
  (new optional input) and `execute_workflow.py` (goal augmentation).
- Cost: at most one Haiku call per goal, and only when the keyword pre-check finds history cues.
- Docs: `specs/zebra-as-is.md`, `zebra-tasks/README.md`.

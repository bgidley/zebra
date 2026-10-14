## Why

The activity view only shows one level of a run: the goal workflow's task list, captured by
polling and recorded when the goal ends. Subflows (`subworkflow`, `parallel`, LLM agent tools)
are invisible, task instances are deleted on completion, and process properties are overwritten
in place, so nothing records what the properties were at each step. Operators can't see each
step that ran across a parent and its subflows, the properties as they were, or where a run is
now (#184).

## What Changes

- **Engine step journal.** The engine appends a `ProcessEvent` at each lifecycle step: process
  started / completed / failed; task waiting (manual), started, suspended, completed, failed.
  Each event carries the process-property diff since the previous event for that process, so
  replaying events rebuilds the properties after any step. Journal write failures are logged and
  never fail a workflow. Large values are stored as a truncated preview.
- **Store support.** `StateStore` gains `save_process_event`, `load_process_events` (no-op
  defaults) and `list_child_processes` (default: scan). Implemented in the in-memory, SQLite,
  Postgres and Django stores; Django migration `0027_process_events` adds
  `zebra_process_events` and an index on `parent_process_id`.
- **Fix:** SQLite and Postgres `save_process` upserts now persist `parent_process_id` /
  `parent_task_id` set after creation (spawners link children that way).
- **Step trace page** `/processes/<id>/trace/` (and `/runs/<run_id>/trace/` redirect): nested
  tree of the run's processes, each subflow under the step that spawned it; per step its state,
  timing, attempts, error and the properties it changed; lazy "properties after this step" and
  "starting properties" snapshots; a "where it is now" panel; live refresh while active. Linked
  from the run detail and run status pages.

## Capabilities

### New Capabilities
- `process-step-journal`: durable per-step event journal with property diffs.
- `run-trace-page`: web view of a run's steps across parent and subflows.

### Modified Capabilities
<!-- none -->

## Impact

`zebra-py` (`core/models.py`, `core/journal.py`, `core/engine.py`, all stores);
`zebra-agent-web` (`storage.py`, `api/models.py` + migration, `api/run_trace.py`,
`web_views.py`, `urls.py`, templates, `format_tags.py`). Journal rows grow with every step;
they are removed with their process.

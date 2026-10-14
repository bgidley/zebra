# Run trace: step journal and trace page (#184)

## 1. Goal and scope

See every step a run took across its parent and subflow processes, the process properties as
they stood after each step, and where the run is now. Issue
[#184](https://gitlab.com/gidley/zebra/-/work_items/184); OpenSpec change `run-trace`.

Before this, the run page showed one level (the goal workflow's tasks, polled by
`execute_goal_workflow` into `__task_executions__` and written to metrics at the end). Task
instances are deleted on completion and properties are overwritten, so nothing kept history.

Not in scope: retention/pruning of journal rows, a cost-per-step column, diffing task-instance
properties (only process properties are journalled), replacing `TaskExecution` metrics.

## 2. Data model

`zebra.core.models.ProcessEvent` (`ProcessEventKind`):

| Field | Notes |
|---|---|
| `id`, `process_id`, `kind` | kind: `process_started`, `process_completed`, `process_failed`, `task_waiting`, `task_started`, `task_suspended`, `task_completed`, `task_failed` |
| `task_instance_id`, `task_definition_id`, `attempt` | task events only |
| `timestamp` | strictly increasing per engine instance |
| `changed`, `removed` | process properties set/changed and keys removed since the previous event for this process |
| `error` | failed task or process |

`zebra/core/journal.py`: `property_diff` (caps a value whose JSON is over 16,000 chars to a
2,000-char preview marked `__journal_truncated__`), `replay` (fold events into the property
dict after each one), `snapshot`.

Storage: `StateStore.save_process_event` / `load_process_events(process_ids)` (no-op defaults,
so third-party stores keep working without history) and `list_child_processes(parent_id)`
(default scans `list_processes`). Tables: SQLite/Postgres `process_events`; Django
`zebra_process_events` (`ProcessEventModel`, column `occurred_at` because `TIMESTAMP` is an
Oracle keyword), migration `0027_process_events`, plus a `parent_process_id` index.
`delete_process` removes a process's events. SQLite and Postgres upserts now also write the
parent link, which spawners set after `create_process`.

## 3. Interfaces

- Web: `/processes/<id>/trace/` (any process; climbs to its root), `/runs/<run_id>/trace/`
  (302 to the root's trace), `/processes/<id>/trace/<event_id>/properties/` (HTMX snapshot).
  "Step trace" button on the run detail and run status pages.
- `zebra_agent_web/api/run_trace.py`: `find_root`, `find_run_root`, `build_trace` →
  `RunTrace(root: TraceProcess, current, process_count, step_count, truncated)`,
  `properties_at`, `split_properties`. Uses only `StateStore`.
- Template filters `seconds` and `pretty_json` (`format_tags.py`).

## 4. Control flow

Engine hook points: `start_process` (after RUNNING), `_create_task` (manual tasks →
`task_waiting`), `_run_task` (`task_started` before the action; `task_suspended` /
`task_completed` / `task_failed` after the output is stored), `complete_task` (human task
completion), `_on_process_terminal` (both the normal end and `fail_process`).

`_journal` diffs `process.properties` against the last journalled properties for that process
(kept in `engine._journal_props`), so changes made between steps are recorded on the next
event and replay is exact. On a cache miss (another engine, restart) it rebuilds the baseline by
replaying stored events. Any exception is logged as a warning; workflows never depend on the
journal.

Trace building: breadth-first over `list_child_processes` (max 200 processes, depth 10, flagged
`truncated`), one `load_process_events` call for all of them, live task instances for
non-terminal processes. Events group into steps by task instance id; a `task_started` after
`task_suspended` is a resume, not a new attempt. Subflows attach to the step whose
`task_instance_id` equals their `parent_task_id`, else under "Subflows not linked to a step".
Steps left running/waiting in a terminal process show as interrupted. "Where it is now" lists
the name path to each current step with no active subflow below it. The page re-fetches the
tree every 5s while the root is active and re-opens expanded `<details>`.

## 5. Configuration

None. Limits are constants: `MAX_JOURNAL_VALUE_CHARS`, `TRUNCATED_PREVIEW_CHARS`
(`zebra/core/journal.py`), `MAX_TRACE_PROCESSES`, `MAX_TRACE_DEPTH` (`api/run_trace.py`).

## 6. Open questions / risks

- **Growth:** every step writes a row whose diff can hold large LLM outputs (capped at 16k
  chars per value). No pruning yet; rows go when their process is deleted.
- Runs from before the journal show the tree and live tasks only.
- `find_run_root` still scans processes by state, like the existing run pages.
- A stale engine cache (two engines driving one process alternately) can leave a key that one
  engine removed in the replay; values stay correct. Acceptable for a single daemon.

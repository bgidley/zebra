## Context

`web_views.dashboard` builds its context from the metrics store and budget manager. Running
state lives only in the workflow process store (`engine.get_store()`).

## Decisions

- **Source of truth is the process store**, not `metrics.get_in_progress_runs()`: a goal is
  "running" iff its top-level process is `RUNNING`. This also covers goals without a metrics row.
- **Group by root**: `store.get_running_processes()` (all depths) is grouped by walking
  `parent_process_id` within the running set. Running children whose root is not running are
  stale state and are not listed.
- **Current tasks** = READY or RUNNING task instances across the tree, shown by task-definition
  name, de-duplicated. A READY task whose definition has `auto: false` marks the goal
  "awaiting input" and its id becomes the link target.
- **Fields**: goal ← `properties.goal`, workflow ← `__workflow_name__`, cost ← `__total_cost__`,
  started ← root `created_at` (rendered with `timesince`). Oldest first, capped at 10.
- **Degrade gracefully**: any failure loading running activities logs a warning and renders the
  empty panel; it never breaks the dashboard.

## Risks

- Cost is O(running processes × tasks) store reads per dashboard load; acceptable at
  single-user scale with the 10-goal cap.

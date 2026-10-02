## Why

`WorkflowEngine.resume_all_processes` flags interrupted non-idempotent tasks with
`__requires_manual_review__` and leaves them RUNNING, but nothing reads the flag. Every daemon
restart bumps `execution_attempt` and the run stays stuck until someone hand-edits the database
(run 11f3f6c1 sat ~4 hours this way in prod). Issue #130.

## What Changes

- Engine: `WorkflowEngine.retry_task(task_id, execute=True)` clears the flag, moves the task
  RUNNING → READY and runs pending auto tasks. `MANUAL_REVIEW_FLAG` constant exported.
- Engine: `resume_all_processes(max_interrupted_attempts=None)` — when a RUNNING task's
  interruption count reaches the cap, the process is failed (`fail_process`) with a clear
  `__error__` instead of being reset/flagged again.
- Setting `RECOVERY_MAX_INTERRUPTED_ATTEMPTS` (env `ZEBRA_RECOVERY_MAX_INTERRUPTED_ATTEMPTS`,
  default 3), passed by the daemon at startup recovery.
- Web: flagged tasks surface on `/activity/` and the run detail page with Retry and Fail buttons
  (HTMX `POST /tasks/<id>/retry/`, `/tasks/<id>/fail/`).
- REST: `GET /api/review-tasks/`, `POST /api/tasks/<id>/retry/`, `POST /api/tasks/<id>/fail/`.

## Capabilities

### New Capabilities

- `crash-recovery-manual-review`: resolving tasks that crash recovery could not safely re-run.

### Modified Capabilities

_(none)_

## Non-goals

- No change to how idempotency is decided (#129 makes `execute_workflow` re-attach to children).
- No generic task-level "fail and continue routing" — Fail ends the run (task-failure routing is #131).

## Impact

`zebra-py/zebra/core/engine.py`, `zebra-agent-web` (daemon, settings, views, templates, urls).

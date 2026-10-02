## Context

Recovery runs once at daemon startup (`run_daemon_loop` → `resume_all_processes`). A task found
RUNNING with an `__idempotency_token__` may already have produced side effects, so recovery flags
it instead of re-running it. The flag had no consumer.

## Decisions

- **Retry is an engine method** (`retry_task`) so the state transition (RUNNING → READY, flag
  cleared) respects the state machine and is reusable outside the web app. `execute=False` lets
  the web layer reset synchronously (errors reported immediately as 404/409) and re-execute on a
  background thread, since the task's action may run for minutes. An in-flight set (thread-locked)
  rejects a second retry of the same task while one is running, so a double-click can't run side
  effects twice; buttons also use `hx-disabled-elt`.
- **Fail ends the run**: the web/API Fail action calls the existing `fail_process` on the task's
  process and every non-terminal ancestor. Failing only the child would leave the parent's
  `execute_workflow` task waiting forever. No new engine task-level fail — avoids overlapping #131.
- **Cap counts interruptions** (`execution_attempt`, incremented each recovery, never reset by
  retry). It applies to idempotent and non-idempotent tasks alike, so a crash-looping task also
  stops. Engine default `None` keeps library behaviour unchanged; the daemon passes the setting.
- Flagged tasks are found via `store.get_running_tasks()` filtered on the flag; the run is
  resolved by walking `parent_process_id` up to the first process with a `run_id`.

## Risks / Trade-offs

- A flagged task left unattended through 3 restarts fails its run — intended, loud > stuck.
- Background retry lives in the web process; a restart mid-retry is a new interruption that the
  next recovery handles (and counts toward the cap).

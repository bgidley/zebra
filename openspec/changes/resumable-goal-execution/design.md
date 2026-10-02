## Context

`execute_goal_workflow` (task `execute_workflow` in `agent_main_loop.yaml`) creates a child
process, links it (`parent_process_id`, `parent_task_id`, `__parent_task_id__`), starts it and
polls it until COMPLETE/FAILED. If the driver dies mid-poll, the parent task stays RUNNING.
`_is_task_idempotent` returns False for any task carrying `__idempotency_token__` (i.e. every task
that started) unless the task definition sets `properties.idempotent: true`; the action-level
`is_idempotent()` hook is never reached for started tasks.

## Decisions

### Re-attach via a child id recorded on the task
The action writes `__child_process_id__` onto its task and saves it *before* starting the child.
On a re-run it loads that process and trusts it only if it is still linked to this parent process
and task. Chosen over scanning for processes by `parent_task_id`: no store has an index/query for
that (it would be a full `list_processes` scan of the prod Oracle table on every run), and the
recorded id is O(1). States: CREATED → start it then wait; RUNNING/PAUSED → wait; COMPLETE/FAILED →
the wait loop returns on its first iteration. Residual window: a crash between `create_process` and
`save_task` leaves an orphan CREATED child and the re-run spawns a fresh one (no duplicate work —
the orphan never started).

### Idempotency via the existing task-definition hint
`idempotent: true` on the `execute_workflow` task in `agent_main_loop.yaml`. This is the mechanism
`_is_task_idempotent` already honours first, so no engine change is needed there (and none in the
area #130 is editing). Re-running is now safe because of re-attach.

### Children recovered before parents
`resume_all_processes` drives each process inline, serially. If a parent were resumed first, its
re-attached `execute_workflow` would poll a child nobody is driving yet until the timeout, then
fail. A stable depth sort (deepest first, by `parent_process_id` within the running set) fixes
this; it is the only engine edit.

### Background recovery in the daemon
`_process_pending_auto_tasks` → `transition_task` runs the rest of each recovered goal inline, so
awaiting `resume_all_processes` before `scheduler_loop.run()` would block the goal queue and
routines for the whole duration of every recovered goal. Recovery now runs as
`asyncio.create_task(recover_interrupted(engine))`; it is cancelled if the daemon stops first
(leaving state as a crash would — recovered again next start).

### Keep `/api/goals/` on its thread (not the daemon queue)
Enqueuing a CREATED process for the `GoalScheduler` would make the daemon own execution, but it
would also put API goals behind budget pacing, priority ordering and the single serial goal slot,
and change the run-status contract (no run row until the daemon picks it up). With the fixes above,
an API goal killed by a redeploy is RUNNING in the store and is recovered by the daemon exactly
like a queued goal, so the simpler change is sufficient.

## Risks / Trade-offs

- **Run status during recovery**: until `assess_and_record` runs, `/api/runs/<id>/status/` returns
  `not_found` for a recovered API goal (the in-memory `_active_api_runs` set died with the old
  process). Pre-existing; the run appears once the recovered goal completes.
- **Stale process locks**: a lock left by the killed driver expires after 30s; recovery inside that
  window raises `LockError` for that process (logged, process left RUNNING until next start).
- **Double driving**: if a standalone `run_daemon` restarts while the web thread is still driving a
  goal, both would run `execute_workflow`; re-attach prevents a duplicate child but the parent
  tasks may both complete. Only one daemon should run (existing operational rule).
- Recovery of an in-flight child's own interrupted LLM task is unchanged (flagged for review, #130);
  the parent then times out waiting (default 120s) and fails rather than hanging.

---
name: f8-crash-recovery
description: Crash recovery contract — write-ahead guarantees, daemon startup recovery, interrupted task handling
metadata:
  type: feature-spec
  issue: "#8"
  requirement: REQ-NFR-002
  status: implemented
---

# F8: Crash Recovery Contract

**GitLab issue**: #8  
**Requirement**: REQ-NFR-002  
**Status**: Implemented

## Goal & scope

Formalise that every state transition is persisted before in-memory signalling fires. Daemon startup recovers processes that were RUNNING when the daemon stopped. Test matrix proves the contract.

## Write-ahead contract

Every state transition in `WorkflowEngine` follows persist-before-signal:

1. **Process state changes**: `process.model_copy(update={state: ...})` → `store.save_process(process)` — then downstream task creation.
2. **Task state changes**: `task.model_copy(update={state: ...})` → `store.save_task(task)` — then action execution or routing.
3. **Task execution**: state set to `RUNNING` and persisted → action runs → result persisted (COMPLETE/FAILED).
4. **Idempotency token**: generated and persisted before the action runs, enabling detection of interrupted non-idempotent tasks.

## Daemon startup recovery

`run_daemon_loop()` calls `engine.resume_all_processes()` immediately after initialisation, before the scheduler loop starts:

```python
resumed = await wf_engine.resume_all_processes(
    max_interrupted_attempts=agent_settings.get("RECOVERY_MAX_INTERRUPTED_ATTEMPTS", 3)
)
if resumed:
    logger.info("Daemon startup: resumed %d interrupted process(es)", len(resumed))
```

`resume_all_processes()` (in `zebra-py/zebra/core/engine.py`):
- Finds all RUNNING processes.
- For each, loads tasks and increments each RUNNING task's `execution_attempt` (interruption count).
- **Cap (#130)**: if a task's `execution_attempt` reaches `max_interrupted_attempts`, the whole
  process is failed via `fail_process` with an `__error__` naming the task and count — no more
  reset/flag cycles. `None` (engine default) disables the cap; the daemon passes the setting.
- Otherwise resets RUNNING tasks:
  - Task with `__idempotency_token__` but no result → **flagged** with `__requires_manual_review__=True` (non-idempotent, human must decide).
  - Task without token → reset to READY (safe to re-execute).
- Cleans up orphaned FOEs (FOEs with no associated tasks).
- Returns the list of recovered processes.

PAUSED processes are intentionally skipped — they require explicit human resumption.

## Manual review of flagged tasks (#130)

Flagged tasks stay RUNNING (the process cannot progress) until a human acts:

- **Engine**: `WorkflowEngine.retry_task(task_id, execute=True)` — requires the task RUNNING with
  `MANUAL_REVIEW_FLAG` (`__requires_manual_review__`) and its process RUNNING, else
  `InvalidStateTransitionError`. Clears the flag, RUNNING → READY, then (if `execute`) runs the
  process's pending auto tasks. `execution_attempt` is kept, so the recovery cap is cumulative.
- **Web helper** `zebra_agent_web/api/manual_review.py`: `find_review_tasks(store, run_id=None)`
  (resolves each task's run by walking up the process tree), `retry_review_task` (reset
  synchronously via `retry_task(execute=False)`, re-execute `transition_task` on a background
  thread), `fail_review_task` (fails the task's process **and all non-terminal ancestors**, since a
  parent's `execute_workflow` task would otherwise wait forever).
- **UI**: activity view shows a "review needed" badge plus an always-visible Retry / Fail row for
  running groups; run detail (`run_detail.html` and `run_pending.html`) shows the same panel
  (`partials/review_tasks.html`). HTMX POSTs to `/tasks/<id>/retry/` and `/tasks/<id>/fail/`.
- **REST**: `GET /api/review-tasks/?run_id=`, `POST /api/tasks/<id>/retry/` (202),
  `POST /api/tasks/<id>/fail/` (optional `{"reason"}` → `__error__`). 404 unknown task, 409 when
  the task is not awaiting review. Same session auth as the other API endpoints.

## Test matrix

11 unit tests in `zebra-py/tests/test_recovery.py` (all passing):

| Test | Coverage |
|------|----------|
| `test_resume_all_processes_no_interrupted` | Empty list on clean state |
| `test_resume_all_processes_simple_workflow` | RUNNING process is returned |
| `test_resume_all_processes_resets_running_tasks` | RUNNING task → READY or flagged |
| `test_resume_all_processes_skips_paused` | PAUSED processes excluded |
| `test_resume_all_processes_multiple_processes` | Bulk recovery |
| `test_resume_all_processes_handles_errors_gracefully` | One bad process doesn't block others |
| `test_recovery_parallel_split_interrupted` | Parallel workflows survive interruption |
| `test_recovery_sync_point_interrupted` | AWAITING_SYNC tasks resolved correctly |
| `test_recovery_partial_parallel_completion` | Mixed branch state handled |
| `test_recovery_non_idempotent_task_flagged` | Token-bearing tasks flagged |
| `test_recovery_foe_orphan_cleanup` | Orphaned FOEs removed |

Manual review (#130): `zebra-py/tests/test_manual_review_recovery.py` (retry_task, cap) and
`zebra-agent-web/tests/unit/test_manual_review.py` (views + REST).

## Configuration

Recovery is automatic on every daemon startup.

| Setting | Env var | Default | Purpose |
|---------|---------|---------|---------|
| `RECOVERY_MAX_INTERRUPTED_ATTEMPTS` | `ZEBRA_RECOVERY_MAX_INTERRUPTED_ATTEMPTS` | 3 | Interruptions after which recovery fails the process (#130) |

## Open questions / risks

- **Cap counts restarts, not executions** — a flagged task awaiting review still accrues an
  interruption per daemon restart, so with the default of 3 an unattended flagged task fails its
  run on the 3rd restart. Intentional: a run stuck that long should fail loudly, not hang.
- **Retry runs in the web process** — the background re-execution thread lives in the web
  server; a web restart mid-retry is itself an interruption handled by the next recovery.
- **Recovery error logging** — if `resume_all_processes()` throws, the daemon logs the exception and continues (fail-open); the process stays RUNNING until manually addressed.
- **No E2E daemon-restart test** — the test matrix covers the engine contract in isolation; an integration test that actually kills and restarts the daemon process is deferred.

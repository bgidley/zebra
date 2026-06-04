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
resumed = await wf_engine.resume_all_processes()
if resumed:
    logger.info("Daemon startup: resumed %d interrupted process(es)", len(resumed))
```

`resume_all_processes()` (in `zebra-py/zebra/core/engine.py`):
- Finds all RUNNING processes.
- For each, loads tasks and resets RUNNING tasks:
  - Task with `__idempotency_token__` but no result → **flagged** with `__requires_manual_review__=True` (non-idempotent, human must decide).
  - Task without token → reset to READY (safe to re-execute).
- Cleans up orphaned FOEs (FOEs with no associated tasks).
- Returns the list of recovered processes.

PAUSED processes are intentionally skipped — they require explicit human resumption.

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

## Configuration

None — recovery is automatic on every daemon startup.

## Open questions / risks

- **Non-idempotent flagged tasks require manual review** — no UI exists yet to surface `__requires_manual_review__` tasks; they must be inspected via the process detail API.
- **Recovery error logging** — if `resume_all_processes()` throws, the daemon logs the exception and continues (fail-open); the process stays RUNNING until manually addressed.
- **No E2E daemon-restart test** — the test matrix covers the engine contract in isolation; an integration test that actually kills and restarts the daemon process is deferred.

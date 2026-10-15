## Why

Continuing failed run e83768ee ("Gear Requirements Gathering") with the comment "Retry" asked
the user every question again (task 4edb7ac3, 15 Oct). The previous run had collected all three
forms and failed only on its final `handoff` llm_call (goal timeout). The continuation assessor
chose `same_workflow`, but `execute_goal_workflow` always spawns a fresh child that starts at the
workflow's first task, so the answers sitting in the failed child were thrown away (#187).

## What Changes

- `WorkflowEngine.start_process` / `start_process_with_timeout` take an optional
  `start_task_ids`: start at those tasks (one flow of execution each) instead of the first task.
- `execute_goal_workflow`, for a `same_workflow` continuation of a run that failed in the same
  workflow, finds that run's failed goal-workflow process, carries its workflow properties and
  `__task_output_*` into the new child, and starts it at the tasks that never completed. The
  child records `__resumed_from__ = {process_id, task_ids}`.
- Falls back to a fresh start when the previous run succeeded, another workflow was chosen, the
  failed process can't be found, or the workflow no longer has those tasks.

## Capabilities

### New Capabilities

### Modified Capabilities
- `goal-continuation`: retrying a failed run in the same workflow resumes where it stopped.

## Impact

`zebra-py/zebra/core/engine.py`, `zebra-tasks/zebra_tasks/agent/execute_workflow.py`. No schema
migration. The lookup scans top-level FAILED/COMPLETE processes for the run id once per retry
(same approach as the run trace's `find_run_root`).

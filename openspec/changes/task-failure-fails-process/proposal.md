## Why

A task that fails (action returns `TaskResult.fail` or raises) is left in `FAILED` and never
routes. The engine's end-of-transition check treated `FAILED` tasks as "done" alongside
`COMPLETE` ones, so when nothing else was active it marked the process **COMPLETE** with no
`__error__`. Parents such as `execute_goal_workflow` then reported success for work that never
happened (prod: FIRE Retirement Calculator child `3bc358af…` — `calculate_fire` FAILED with a
`NameError`, process COMPLETE). Issue #131.

## What Changes

- When a transition leaves no active tasks and at least one task is `FAILED`, the engine marks
  the process **FAILED** instead of COMPLETE, setting `__error__` to the task's error and
  `__failed_task__` to its task definition id.
- Applies on every path that ends in `transition_task`: `start_process`, `complete_task`
  (human tasks, including a human task completed with a failure result) and post-recovery
  execution after `resume_all_processes`.
- Handled failures are unchanged: a task that returns success with a `next_route` (e.g.
  `"failed"`) still routes and the process completes normally.
- `execute_goal_workflow` already maps a FAILED child to a failed result carrying `__error__`;
  now covered by a real-engine test.

## Capabilities

### New Capabilities

- `process-failure-propagation`: an unhandled task failure fails its process.

### Modified Capabilities

_(none)_

## Non-goals

- No new YAML failure-routing construct (e.g. `on_failure:`); workflows that want to recover
  keep returning success + `next_route`.
- No retroactive fix-up of processes already stored as COMPLETE with FAILED tasks.
- The destruct action is not run on this failure path (consistent with `fail_process`).

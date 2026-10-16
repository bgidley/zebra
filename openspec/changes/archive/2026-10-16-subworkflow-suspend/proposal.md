## Why

#146 gave the engine a durable way for a task to wait on child processes (`TaskResult.suspend`),
and #185 moved `execute_goal_workflow` onto it. `subworkflow`, `wait_subworkflow` and
`parallel_subworkflows` still hold a coroutine and poll the child every 0.1s, so Zebra has two
parent/child mechanisms. A polling task stays RUNNING while its child waits on a human, so
restarts count as interruptions, its wait is lost on restart, and failing the parent while it
polls leaves the wait coroutine running (#181).

## What Changes

- `subworkflow` (`wait: true`), `wait_subworkflow` and `parallel_subworkflows` return
  `TaskResult.suspend([...])` instead of polling. The engine re-runs them with `subflow_results`
  once every child is terminal; they build the same result dicts as before from those.
- Outputs are unchanged: `process_id`, `success`, `properties`, `output` (the child's
  `__output__`), `error`; `parallel_subworkflows` keeps its keyed results and
  `partial_failure` / `failure` routes.
- `timeout` now bounds each child's inline auto-task chain (`start_process_with_timeout`, as
  `execute_goal_workflow` does), for `wait: false` too. Time a child spends parked on a human
  task is no longer counted. A timed-out child fails, and the waiting task reports its error.
- `wait_subworkflow` waits only for a child of its own process; any other process id fails the
  task. Its `timeout` is ignored with a warning: the child was started (and bounded) elsewhere.
- `parallel_subworkflows` `fail_fast`: stops starting further children once one fails, and
  returns once those started have finished (it no longer returns while children still run).
- Engine: when a child finishes, every suspended task in its parent process that waits on it is
  resumed, not only the child's `parent_task_id` — `wait_subworkflow` waits on a child another
  task spawned.

## Capabilities

### New Capabilities
- `subworkflow-actions`: the `subworkflow`, `wait_subworkflow` and `parallel_subworkflows` actions.

### Modified Capabilities
- `subflow-suspension`: a finished child resumes any task of its parent process waiting on it.

## Impact

`zebra-tasks/zebra_tasks/subtasks/` (all three actions plus a shared helper),
`zebra-py/zebra/core/engine.py` (`_on_process_terminal`). No schema migration. No shipped
workflow uses these actions; a task polling at deploy is RUNNING and is re-run (or flagged) by
recovery as before.

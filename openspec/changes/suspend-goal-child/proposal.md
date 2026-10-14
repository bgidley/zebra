## Why

Goal ca42c3c6 (13 Oct) was failed by the 900s goal timeout while its child workflow waited on a
human task. `execute_goal_workflow` polled the child inline, so the goal's `start_process` never
returned while the human answered and the goal timeout fired. `fail_process` only cascades to
children of `AWAITING_SUBFLOW` tasks, so the child stayed RUNNING with its human tasks listed;
answering them a day later completed an orphan and the goal never resumed or showed in Activity.
The same polling kept the task RUNNING across deploys, so restarts counted as interruptions and
other goals hit the recovery cap ("interrupted 3 times") while waiting on a human (#185).

## What Changes

- `execute_goal_workflow` starts the child (still bounded by its `timeout`) and returns
  `TaskResult.suspend([child])` instead of polling. The engine re-runs it with `subflow_results`
  once the child is terminal; the result (output, cost, tokens, user inputs, task executions) is
  built from the child then. A goal parked on the child's human task returns from its bounded run.
- `fail_process` also fails every non-terminal child linked by `parent_process_id`, not just those
  a suspended task waits on. New `StateStore.get_child_processes()` (default filters
  `list_processes`; `DjangoStore` queries it).
- Removes the #183 wait-loop timeout: the parent no longer waits, so a hang in the child after a
  human submit is bounded only by the LLM client timeouts (#183).

## Capabilities

### New Capabilities

### Modified Capabilities
- `goal-execution-timeouts`: goal timeout no longer covers a human wait in the goal workflow; the
  wait-loop timeout is removed.
- `subflow-suspension`: failing a process fails all its live children.
- `goal-crash-recovery`: re-attaching suspends on the recorded child instead of waiting on it.

## Impact

`zebra-tasks/zebra_tasks/agent/execute_workflow.py`, `zebra-py/zebra/core/engine.py`
(`fail_process`), `zebra-py/zebra/storage/base.py`, `zebra-agent-web/zebra_agent_web/storage.py`.
No schema migration. Goals in flight at deploy have their task RUNNING; recovery re-runs it
(idempotent), it re-attaches to the recorded child and suspends.

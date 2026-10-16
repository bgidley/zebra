## Context

See `specs/llm-agent-tools-design.md` (#146) for the suspend mechanism and #185 for
`execute_goal_workflow`, which this follows.

## Decisions

- **Actions still start their children.** As today, each action creates the child, links it
  (`parent_process_id`, `parent_task_id`) and starts it inline, bounded by `timeout` if set. Then
  it suspends. The engine resumes immediately when the child is already terminal (#185), so a
  child that finishes inline costs one extra action run, no wait. Leaving children CREATED for the
  engine to start would also work, but would make `timeout` and `fail_fast` need engine support.
- **Results are built from the child's properties** (`__output__`, `__error__`) in
  `subflow_results`, not from the engine's `output` field (which honours `result_key`), so
  outputs match the polling versions exactly.
- **`parallel_subworkflows` keys** are kept on the task (`__subflow_keys__`: child id → key);
  task properties persist across the suspend.
- **Resume lookup.** `_on_process_terminal` resumes the child's `parent_task_id` plus any
  AWAITING_SUBFLOW task of the parent process listing the child. One extra
  `load_tasks_for_process` per child that finishes.
- **`wait_subworkflow` on a non-child** fails: nothing would resume the task when an unrelated
  process finishes. No shipped workflow does this.

## Risks

- `timeout` semantics change (inline chain, not wall clock). Same trade #142/#185 made for goals.

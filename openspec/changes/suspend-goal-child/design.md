## Context

`execute_goal_workflow` (Agent Main Loop) ran its child inline and then polled it, resetting its
own timeout while the child had a pending human task. Callers bound the goal run with
`start_process_with_timeout` (#142); that bound only "pauses" when `start_process` returns, which a
polling action never does. #146 added `TaskResult.suspend` for `llm_agent` tool calls.

## Decisions

- **Suspend after the inline start.** The action still starts the child itself with
  `start_process_with_timeout(child, timeout)` so the per-workflow `timeout` and #140's "timed-out
  child is data" keep working, then returns `suspend([child])`. A child that finished inline is
  terminal before the suspend, so the engine resumes the task as soon as the parent's lock is
  released (`_start_subflows` → `_resume_if_subflows_done`). The child's terminal hook fires while
  the parent task is still RUNNING and is a no-op.
- **Result on resume.** `_collect_child` reads the child (`CHILD_PROCESS_ID_KEY`) and its stored
  definition, and builds the same result dict as before, plus `__task_executions__` and
  `task_completed` progress events from its `__task_output_*` keys.
- **Re-attach (F129).** An existing linked child is started if CREATED and suspended on whatever its
  state, so recovery of a pre-#185 RUNNING task converts it to a suspended wait.
- **Cascade by link, not only by wait.** `fail_process` unions the suspended tasks' pending children
  with `get_child_processes(process_id)`. That covers a child spawned by an action that is still
  running when the parent fails. `DjangoStore` does not user-scope it: the parent id scopes it.

## Risks / Trade-offs

- The chain a human submit drives runs inside `complete_task` (often the web request) and is no
  longer bounded by the parent's wait; hung LLM calls are bounded by `ZEBRA_LLM_TIMEOUT_SECONDS`.
  The resumed goal's remaining tasks also run there, as they already did for ethics-dilemma forms.
- Live progress during the child run (`task_completed`) is emitted in a batch on resume.

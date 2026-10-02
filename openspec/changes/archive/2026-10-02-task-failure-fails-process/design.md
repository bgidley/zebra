## Context

`WorkflowEngine.transition_task` processes a stack of auto tasks under the process lock, then
loads all task instances and, if none are outside `{COMPLETE, FAILED}`, calls
`_complete_process`. Completed tasks are deleted after routing; a FAILED task is never routed
and never deleted, so it lingers as the only evidence of failure. The check therefore saw "no
active tasks" and completed the process.

All entry points (`start_process`, `complete_task`, `_process_pending_auto_tasks` after
`resume_all_processes`) converge on `transition_task`, so the bug — and the fix — is path
independent. Recovery was a red herring in the prod incident.

## Decisions

- **Fix at the single completion check.** If no active tasks remain and any FAILED task
  exists, call a new `_fail_process_for_task(process, task)` instead of `_complete_process`.
  One small, local edit in `engine.py` — minimises conflict with concurrent #129/#130 work.
- **`__error__` = the task's own error** (fallback `"Task '<def id>' failed"`), plus
  `__failed_task__` = task definition id, so parents (`execute_goal_workflow`) and the UI show
  the real cause.
- **Wait for siblings.** In parallel workflows a failed branch does not abort siblings; the
  process fails once the remaining branches have drained (sync joins already treat FAILED
  tasks as non-blocking). Keeps the change minimal; fail-fast can come later if wanted.
- **No destruct on failure**, matching `fail_process`.
- **Explicit failure routing is unaffected**: a task signalling failure via
  `TaskResult(success=True, next_route=...)` is COMPLETE and routes normally.

## Risks

- Behaviour change: three `test_full_coverage.py` tests had pinned the old COMPLETE outcome
  (coverage tests, not design intent); they now assert FAILED.
- Workflows that relied on a failed parallel branch still yielding COMPLETE will now FAIL.
  No such workflow found in the repo.

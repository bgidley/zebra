## Context

The engine processes auto tasks on a stack inside `transition_task` while holding the process lock; `start_process` returns only when the chain completes or reaches a manual task. Callers' poll loops therefore never bounded execution. Actions are async (LLM HTTP calls, sleeps), so asyncio cancellation reaches them at their next await; the engine has no `except BaseException`, and `store.lock` releases in a `finally`.

## Decisions

- **One engine helper, not per-caller `wait_for`.** The daemon needs a periodic kill-switch check, and nested runs (main loop → child workflow) need cancellation to fail the child too. `start_process_with_timeout` covers deadline, cancel-check polling and caller cancellation in one place; callers keep their existing post-start poll loops for human-task waits.
- **Fail, don't just cancel.** A cancelled chain leaves a RUNNING task; `fail_process` marks all non-terminal tasks FAILED and sets `__error__` (`Timed out after Ns`, `Kill switch activated`, `Cancelled by caller`), so the process is terminal and recovery won't re-drive it.
- **Human-task time is excluded.** The bound covers only the inline chain. Waiting on a human remains governed by the existing post-start polling (and #141).
- **Defaults are generous and configurable.** Prod run-duration data was not available when choosing them; child workflow 600s < goal 900s so a child timeout still leaves time for assess/record.

## Risks

- A legitimate goal workflow longer than 600s will now fail. Mitigation: raise `timeout` in the YAML / `ZEBRA_GOAL_TIMEOUT_SECONDS`.
- CPU-bound synchronous code inside an action cannot be cancelled until it yields.
- Overlaps with #141 (daemon human-task handling) in `daemon._tick`; this change touches only the start phase.

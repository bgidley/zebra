## Context

`start_process_with_timeout` (#142) bounds a child's *first* inline chain only. Once the child
parks on a human task and the user submits, `complete_task` runs the remaining auto tasks inline
in the web request with no bound. `execute_goal_workflow._wait_for_completion` is then the only
watcher, and on timeout it just returned.

## Decisions

- **Per-attempt client timeout, not streaming.** A float `timeout` on `AsyncAnthropic` /
  `AsyncOpenAI` is the smallest change. Non-streaming requests receive no bytes until generation
  ends, so the value must exceed the longest legitimate call: the largest `max_tokens` in use is
  4096 (+4096 thinking headroom on Sonnet/Haiku), well under 180s. Overridable via
  `ZEBRA_LLM_TIMEOUT_SECONDS`. Switching `complete()` to streaming with an idle timeout would be
  more precise; deferred until a legitimate call needs longer.
- **Fail the child from the parent.** `_time_out_child` calls `engine.fail_process` (no lock
  needed). The hung coroutine cannot be cancelled from here (it lives in another request/task).
- **Engine guard.** `_run_task` reloads the process after the action; if it is terminal the result
  is dropped (the task is already FAILED by `fail_process`). `_transition_locked` skips its
  complete/fail decision for an already-terminal process. Cost: one extra `load_process` per task.

## Risks

- A legitimately slow call over 180s now fails after three attempts. Raise
  `ZEBRA_LLM_TIMEOUT_SECONDS` if seen.
- The extra `load_process` per task adds one DB read per auto task.

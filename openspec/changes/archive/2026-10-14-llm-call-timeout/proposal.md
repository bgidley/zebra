## Why

Run e83768ee ("Gear Requirements Gathering", opus) failed with `Timeout after 600.0s` after the
user had answered every form: the last `llm_call` hung. The LLM SDKs default to a 600s timeout
per attempt plus 2 retries, so one stalled request outlived the 600s goal budget. The chain after
a human form runs inline in `complete_task`, outside `start_process_with_timeout`, so on timeout
`execute_goal_workflow` returned but left the child running (recovery failed it an hour later),
and the run recorded $0 although the child had spent ~$0.20 (#183).

## What Changes

- Every LLM provider (Anthropic, OpenAI, OpenRouter, Kimi) bounds each API attempt with
  `llm_request_timeout()`: `ZEBRA_LLM_TIMEOUT_SECONDS`, default 180s, 2 retries — three attempts
  fit inside a 600s goal.
- On timeout `execute_goal_workflow` fails the child process and reports the child's
  cost/tokens instead of zeros.
- The engine discards an action's result when its process was failed while the action ran
  (no routing on a dead process; no stale save reverting it to RUNNING).

## Capabilities

### New Capabilities

### Modified Capabilities
- `goal-execution-timeouts`: timeouts after a human task fail the child and keep its cost;
  bounded LLM attempts; late results on failed processes are discarded.

## Impact

`zebra-tasks/zebra_tasks/llm/` (base, providers), `zebra_tasks/agent/execute_workflow.py`,
`zebra-py/zebra/core/engine.py` (`_run_task`, `_transition_locked`). New env var
`ZEBRA_LLM_TIMEOUT_SECONDS` (optional).

## 1. Bounded LLM calls

- [x] 1.1 `llm_request_timeout()` / `ZEBRA_LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` in `llm/base.py`
- [x] 1.2 Pass `timeout` + `max_retries` in Anthropic, OpenAI, OpenRouter and Kimi providers

## 2. Goal workflow timeout

- [x] 2.1 `execute_goal_workflow` fails the child on timeout and reports its cost/tokens

## 3. Engine

- [x] 3.1 `_run_task` discards a result when the process became terminal during the action
- [x] 3.2 `_transition_locked` skips complete/fail for an already-terminal process

## 4. Tests & docs

- [x] 4.1 `test_llm_timeout.py`, `test_fail_during_action.py`, hang-after-human-task test
- [x] 4.2 `specs/zebra-as-is.md`, root and zebra-tasks AGENTS.md, `.env.example`

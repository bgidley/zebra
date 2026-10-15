## 1. Actions

- [x] 1.1 `assess_stuck`: route `proceed` / `ask_human`, help budget, LLM help request with fallback
- [x] 1.2 `apply_help_response`: route `retry` / `redirect` / `abandon`, record `__help_history__`
- [x] 1.3 `with_help_guidance` appended to the child goal in `execute_goal_workflow`
- [x] 1.4 Entry points in `zebra-tasks/pyproject.toml`

## 2. Workflow

- [x] 2.1 `agent_main_loop.yaml`: `assess_stuck` → `stuck_help_request` → `apply_help_response`, version 16

## 3. Tests & docs

- [x] 3.1 Unit tests for both actions and `with_help_guidance`
- [x] 3.2 Main-loop tests: park, retry→complete, redirect, abandon, budget spent
- [x] 3.3 `specs/zebra-as-is.md`, zebra-agent / zebra-tasks AGENTS.md

## 1. Helper

- [x] 1.1 `zebra_tasks/llm/structured.py`: `parse_llm_json`, `complete_json`, `LLMJSONError`
- [x] 1.2 Tests for the helper: unterminated fence, prose, truncated → retry with 2× tokens, prose → JSON-only retry, both fail

## 2. Dream-cycle steps

- [x] 2.1 `workflow_evaluator`: `complete_json`, `max_tokens` 8000 property, `parse_failure`, cause in key issue, cost into `__total_cost__`
- [x] 2.2 Curator duplicate check, knowledge review, improvement proposals: `complete_json`, cause recorded
- [x] 2.3 Tests for each action

## 3. Docs & delivery

- [x] 3.1 `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`
- [x] 3.2 Run `ruff check --fix` + `ruff format`, full unit tests, before committing

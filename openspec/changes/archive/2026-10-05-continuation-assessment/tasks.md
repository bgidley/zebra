> Branch: `f135/continuation-assessment`. Reference `#135` in commits.

## 1. Implementation

- [x] 1.1 `continuation_assessor` action (inputs/outputs, reversibility hint, model resolution, fallbacks)
- [x] 1.2 Register the entry point in `zebra-tasks/pyproject.toml`
- [x] 1.3 `agent_main_loop.yaml` v8: add the `assess_continuation` step and its routes
- [x] 1.4 Run detail: the `_continuation_decision.html` partial and the view context

## 2. Tests & docs

- [x] 2.1 Action tests: all three routes, the non-continuation bypass, LLM failure, a missing workflow
- [x] 2.2 Main loop integration tests for each route
- [x] 2.3 Template render test
- [x] 2.4 Update `specs/zebra-as-is.md`

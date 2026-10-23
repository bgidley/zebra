## 1. Prior outputs

- [x] 1.1 `followup.py`: `prior_outputs_from(properties)` — drop `__*`, `goal`, `prior_outputs`; cap strings at 8000, drop larger values, total cap 32000
- [x] 1.2 `execute_workflow.py`: on a continuation find the previous run's goal-workflow process (completed or failed, generalising `_previous_child`), set `prior_outputs` on the child, bind `from_prior` inputs; missing process → warn and carry on
- [x] 1.3 Tests: template reads `prior_outputs`; non-continuation has none; caps and exclusions; `from_prior` binding and missing key; missing process

## 2. Workflow authors

- [x] 2.1 Creator and optimizer prompts mention `prior_outputs` / `from_prior`; test asserts it

## 3. Docs and checks

- [x] 3.1 `zebra-tasks/AGENTS.md` (`ExecuteGoalWorkflowAction`), `specs/zebra-as-is.md`
- [x] 3.2 ruff, unit tests, `openspec validate continuation-prior-outputs --strict`

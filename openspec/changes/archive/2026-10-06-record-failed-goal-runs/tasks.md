## 1. Actions

- [x] 1.1 Add `continue_on_failure` to `execute_goal_workflow` (child FAILED, timeout, exception paths)
- [x] 1.2 Add `propagate_failure` action and register entry point

## 2. Agent Main Loop

- [x] 2.1 Workflow v7: `continue_on_failure: true`, pass `error` to `assess_and_record`, add terminal `report_outcome`
- [x] 2.2 `AgentLoop` surfaces `execution_result.error`

## 3. Tests and docs

- [x] 3.1 Action tests (continue_on_failure, propagate_failure)
- [x] 3.2 Main-loop test: failed goal workflow runs assess/memory and ends FAILED with child error
- [x] 3.3 Update `specs/zebra-as-is.md`

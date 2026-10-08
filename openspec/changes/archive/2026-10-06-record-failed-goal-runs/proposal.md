## Why

When a goal's workflow fails, `execute_goal_workflow` returns `TaskResult.fail`, the engine stops routing from that task and the Agent Main Loop process ends FAILED (#131). `assess_and_record`, `ethics_post_review` and `update_conceptual_memory` never run, so failed runs produce no metrics row and no workflow/conceptual memory entry — the agent cannot learn from failures and success rates only ever see successes. Issue #140.

## What Changes

- `execute_goal_workflow` gains an opt-in `continue_on_failure` property. When true and the child workflow fails (child FAILED, timeout, or execution error), the action completes successfully with `success: false` and the error in its output instead of failing the task. Default stays false, so existing callers and #131 behaviour are unchanged.
- New `propagate_failure` task action: fails with the given `error` when `success` is false, succeeds otherwise.
- Agent Main Loop (v10): `execute_workflow` sets `continue_on_failure: true`; `assess_and_record` receives `error`; a new terminal `report_outcome` task (action `propagate_failure`) after `update_conceptual_memory` fails with the child's error, so the process still ends FAILED with the child's `__error__` — but only after the failure was recorded and learned from.
- `AgentLoop` surfaces `execution_result.error` in `AgentResult.error` for completed processes.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `process-failure-propagation`: parent workflow execution may opt in to recording child failure as output; the Agent Main Loop records failed runs before ending FAILED.

## Impact

- `zebra-tasks/zebra_tasks/agent/execute_workflow.py`, new `zebra-tasks/zebra_tasks/agent/propagate_failure.py`, `zebra-tasks/pyproject.toml` (entry point)
- `zebra-agent/workflows/agent_main_loop.yaml`, `zebra-agent/zebra_agent/loop.py`
- No data model or migration changes. Failed runs now create `WorkflowRun` (success=false) and workflow memory rows.

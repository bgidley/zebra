## Why

When a goal continues a previous run (#134), Zebra currently runs the normal selector as if the goal were new. It does not decide whether to reuse the previous workflow, pick another library workflow, or create a new one, and it records no reason. Implements #135.

## What Changes

- New `continuation_assessor` task action. It reads the `previous_run_context` property (previous goal, workflow, success, output and task progress if present) and the `continuation_comment` property, and asks the LLM to pick `same_workflow`, `existing_workflow` or `new_workflow` with a short rationale.
- The action sets the `continuation_decision` and `continuation_rationale` process properties. These are already copied onto the `WorkflowRun` (foundation commit), so they persist and the dream cycle can read them.
- `agent_main_loop.yaml` v8: `ethics_input_gate` (proceed) → `assess_continuation`. Routes: `not_continuation` and `existing_workflow` → `select_workflow`; `same_workflow` → `flag_concerns`; `new_workflow` → `create_workflow`.
- `same_workflow` falls back to `existing_workflow` when the previous workflow is no longer in the library. A missing provider or an LLM or parse failure also falls back to `existing_workflow`, with a warning.
- The run detail page shows the decision and rationale in a new `_continuation_decision.html` partial.

## Capabilities

### New Capabilities
- `continuation-assessment`: how a continued goal chooses a workflow, and how that choice is recorded and shown.

### Modified Capabilities
<!-- none -->

## Non-goals

- Starting continuations or building the task-progress list (#134).
- Showing the run chain (#134).
- Resuming a workflow partway through. `same_workflow` re-runs the previous workflow from the start, with the previous run's context.

## Impact

`zebra-tasks/zebra_tasks/agent/continuation_assessor.py`, `zebra-tasks/pyproject.toml`, `zebra-agent/workflows/agent_main_loop.yaml`, `zebra-agent-web` (the run detail view and templates), and tests. Branch: `f135/continuation-assessment`.

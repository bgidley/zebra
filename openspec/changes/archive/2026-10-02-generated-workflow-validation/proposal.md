## Why

Run `51dc4a86` (FIRE goal) created a workflow that completed after its first human form. `WorkflowCreatorAction` capped output at 2000 tokens (variant creator: 2500). Multi-form workflows overflow; the truncated YAML still parsed but lost its trailing `routings` block, so the first task had no outbound routes and the process silently completed. Closes #122.

## What Changes

- Workflow generators (`workflow_creator`, `workflow_variant_creator`) use a shared `GENERATED_WORKFLOW_MAX_TOKENS = 8000`.
- A generated workflow is rejected (task fails, nothing saved to the library) when the LLM `finish_reason` is `max_tokens`/`length`, or when `validate_definition` reports errors (orphaned tasks, under-joined synchronized tasks).

## Capabilities

### New Capabilities
- `generated-workflow-validation`: generated workflow definitions must be complete and structurally valid before use.

### Modified Capabilities
<!-- none -->

## Non-goals

- Automatic retry/repair of a rejected generation.
- Validating hand-written library workflows.

## Impact

`zebra-tasks/zebra_tasks/agent/creator.py`, `variant_creator.py`. Branch: `f122/creator-truncated-workflows`.

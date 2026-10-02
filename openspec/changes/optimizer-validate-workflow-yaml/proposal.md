## Why

On 2026-10-02 the prod dream cycle asked the LLM to rewrite "FIRE Retirement Calculator". The reply was cut off at about 6 KB (the optimizer capped output at 2000 tokens), yet `workflow_optimizer` saved it as `fire_retirement_calculator_1.yaml` without parsing it. The library silently skips the invalid file, but `changes_made` and the dream summary still said the root cause was fixed. Closes #128.

## What Changes

- `workflow_optimizer` requests `GENERATED_WORKFLOW_MAX_TOKENS` (8000). When the response is truncated (`finish_reason` is `max_tokens` or `length`), it retries once with double the budget.
- Every created or modified workflow is validated before it is saved: it is parsed with `load_definition_from_yaml` and checked with `check_generated_workflow` (truncation plus `validate_definition`), and every task `action` must be registered in `context.engine.actions`.
- Rejected changes are not saved and are not listed in `changes_made`, `new_workflows` or `modified_workflows`. They go into a new `failed_changes` output with the reason.
- The `dream_cycle.yaml` (v3) summary prompt reports failed changes and tells the LLM not to claim them as applied.
- `_clean_yaml_response` no longer raises when a code fence is unterminated, which is a sign of truncation.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `generated-workflow-validation`: now also covers the dream-cycle `workflow_optimizer`.

## Non-goals

- Changing how modified workflows are named on disk (they are still saved with a `_N` suffix next to the original).
- Repairing invalid output beyond the single truncation retry.

## Impact

`zebra-tasks/zebra_tasks/agent/optimizer.py`, `zebra-agent/workflows/dream_cycle.yaml`, tests in `zebra-tasks/tests/`. Branch: `f128/dream-optimizer-validate-yaml`.

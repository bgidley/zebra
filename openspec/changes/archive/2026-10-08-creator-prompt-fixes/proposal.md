## Why

A review of the `workflow_creator` prompt (#139) found that it tells the LLM things the engine does not do. Top-level `result_key` (which the prompt asks for) is dropped by the loader, so generated workflows show a raw property dump. The yes/no advice says an enum field drives routing, but routes come from route-name buttons. The prompt never explains output shapes, serial vs parallel routing, joins, or that only human tasks can pick a `route_name`. A single parse/validation error kills the goal with no repair attempt.

## What Changes

- Loader: a top-level `result_key` is copied into `definition.properties` (an explicit `properties.result_key` wins).
- Creator prompt: adds data flow (string vs dict outputs, `{{key.field}}`), routing semantics (first serial route wins, `parallel: true`, `synchronized: true`, `route_name` only after human tasks), corrected human-decision guidance, side-effect guidance for file/python actions, and a worked multi-step example.
- Creator: temperature 0.7 → 0.3; one repair attempt that feeds the parse/validation error back to the LLM. Truncation still fails immediately.

## Capabilities

### New Capabilities
- `workflow-creator-prompt`: what the creator system prompt must tell the LLM, and how top-level `result_key` is honoured.

### Modified Capabilities
- `generated-workflow-validation`: invalid generated workflows get one repair attempt before failing.

## Impact

- `zebra-py/zebra/definitions/loader.py`
- `zebra-tasks/zebra_tasks/agent/creator.py`
- Tests in `zebra-py/tests/test_loader.py`, `zebra-tasks/tests/test_workflow_creator.py`
- Backward compatible: `properties.result_key` still works; existing YAML unaffected.

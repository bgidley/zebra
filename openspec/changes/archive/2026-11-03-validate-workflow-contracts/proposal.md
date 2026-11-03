## Why

The engine accepts workflows whose output contracts are broken and runs them silently (#271, from
the dream cycle's `improvement_priorities`). `validate_definition` checks only graph shape.
`ExecutionContext.resolve_template` turns a missing `{{task.output}}` or `{{prop.key}}` into an
empty string, so a branch that never ran, a typo'd key, or a subworkflow that returned a different
shape produces a blank prompt or a misleading "complete" result.

## What Changes

- **Static check at load time** in `zebra.definitions.loader`: a new `validate_contracts(definition,
  registry=None)` returns warnings/errors for `{{...}}` references in task properties that name no
  task, no declared process property and no known runtime key, and for references to a task output
  that is not produced on every path to the referencing task (branch-specific outputs, honouring
  `synchronized` joins). Declared `outputs` of an action (`ParameterDef`) are checked for
  `{{task.output.key}}` references. Findings carry a severity: `error` for a reference to an
  unknown task or an output that exists on no path; `warning` for one that exists on only some paths.
- **Run-time check** in `resolve_template`: a reference that resolves to nothing is logged and
  recorded on the process (`__contract_violations__`) instead of vanishing. A per-workflow
  `strict_templates: true` property makes it fail the task with `TaskResult.fail`.
- **Structured outputs**: an `llm_call` with `response_format: json` and an `output_schema` property
  has its parsed result validated against the JSON Schema; a mismatch fails the task with the
  validation errors.
- **Subworkflow return shape**: `subworkflow` may declare `expects: [keys]`; a child result missing
  a key fails the parent task naming the key.
- Library saves (`WorkflowLibrary.save`) reject definitions with `error` findings, so the optimizer
  and dream cycle cannot add broken contracts; built-in workflows are fixed or annotated to pass.

## Capabilities

### New Capabilities
- `workflow-contracts`: static and run-time validation of template references, branch-specific
  outputs, structured-output schemas and subworkflow return shapes.

### Modified Capabilities
<!-- None: existing validate_definition checks are unchanged. -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A template reference to an unknown task or to an output no path produces is reported at load/save time, before execution | Unit tests: a YAML with `{{ghost.output}}` and one referencing a task on a never-taken branch yield `error` findings naming task and reference; a valid workflow yields none |
| O2 | A reference to an output produced on only some paths to the referencing task is flagged as a warning; a synchronized join of all branches, or an output every path produces, is not | Tests over branch/merge fixtures: warning for a branch output used after a plain merge, none for a synchronized join or an output produced on every path |
| O3 | At run time an unresolved template is no longer silent: it is logged and recorded as `{task, ref}` entries in the *process* property `__contract_violations__`, and raises (failing the task) under `strict_templates` | Engine test: workflow with a missing key has `__contract_violations__ == [{"task": "a", "ref": "typo_key"}]`; with `strict_templates: true` the task error contains `{{typo_key}}` |
| O4 | An `llm_call` JSON output that violates its declared `output_schema`, or a subworkflow result missing an `expects` key, fails the task with a clear message | Tests assert exact substrings: `missing required key 'sentiment'` for `llm_call` (mock provider), `missing expected key(s): summary` for `subworkflow`; conforming output passes |
| O5 | All built-in workflows pass the static check and the library rejects new broken ones | A test loads every built-in workflow and asserts no `error` findings; `WorkflowLibrary.save` of a broken definition raises `WorkflowContractError` and writes nothing |

## Non-goals

No type system for process properties, no change to the template syntax, and no retroactive
rewriting of workflows already in a deployed library (they get warnings in the log, not a refusal
to run).

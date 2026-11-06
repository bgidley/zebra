# Workflow output contracts (#271)

## Goal & scope
Stop broken `{{...}}` references and result shapes running silently. Does not add a type system for
process properties or change template syntax; workflows already in a deployed library only log
warnings. GitLab #271; OpenSpec change `validate-workflow-contracts`.

## Data model changes
- Process property `__contract_violations__`: list of `{"task": id, "ref": "a.b"}`, deduplicated.
- Optional `strict_templates: true` in process properties or the definition's `properties`.
- Task properties: `llm_call.output_schema` (with `response_format: json`), `subworkflow.expects`.

## API / interface changes
- `zebra.definitions.contracts`: `validate_contracts(definition) -> list[ContractFinding]`
  (`severity` `error`/`warning`), `validate_output_schema(schema, value) -> list[str]` (JSON Schema
  subset: type, enum, required, properties, items; `jsonschema` is not a dependency).
- `zebra.core.exceptions.TemplateResolutionError`.
- `WorkflowLibrary.save` raises `WorkflowContractError` (a `ValueError`) on `error` findings.

## Control flow
- Static: a must/may dataflow over routings. A task reached by any one incoming routing
  guarantees the intersection of its predecessors' outputs; a `synchronized` join the union.
  `{{x.output}}`: `x` not a task and not a property written by a `*_key` task property = error;
  `x` in no path = error; only in some = warning. Other undeclared roots = warning.
- Run time: `resolve_template` logs and records a reference with no value; under strict mode it
  raises, and the engine fails the task with the reference in the error.
- `llm_call` fails with `output_schema` violations; `subworkflow` fails with
  `missing expected key(s): ...` when the child's `__output__` lacks an `expects` key.

## Configuration
`strict_templates` (per workflow / process, default off). No settings or env vars.

## Open questions / risks
- `{{task.output.key}}` is not checked against an action's declared `outputs` (the runtime does not
  resolve that form).
- Optional properties that are legitimately absent are recorded as violations; they only fail under
  `strict_templates`.

# workflow-contracts Specification

## Purpose
TBD - created by archiving change validate-workflow-contracts. Update Purpose after archive.

## Requirements

### Requirement: Static template reference validation
`validate_contracts` SHALL scan every string in task properties for `{{...}}` references and report
an `error` finding for a reference to a task that does not exist, and for a `{{task.output}}`
reference to a task that cannot have run on any path to the referencing task.

#### Scenario: Unknown task
- **WHEN** a task prompt contains `{{ghost.output}}` and no task `ghost` exists
- **THEN** `validate_contracts` returns an error naming the task and the reference

#### Scenario: Valid workflow
- **WHEN** every reference names an upstream task or a declared property
- **THEN** no findings are returned

### Requirement: Branch-specific output availability
`validate_contracts` SHALL report a `warning` when a referenced task output is produced on only some
paths to the referencing task, and SHALL NOT warn when every path produces it.

#### Scenario: Output from one branch used after merge
- **WHEN** only the "approved" branch runs task `draft` and a later merge task references `{{draft.output}}`
- **THEN** a warning names `draft` and the merge task

### Requirement: Run-time unresolved template reporting
`resolve_template` SHALL record each reference that resolves to nothing in the process property
`__contract_violations__` and log it. When the process property `strict_templates` is true the
task SHALL fail naming the reference.

#### Scenario: Strict mode
- **WHEN** `strict_templates` is true and a task template references a missing key
- **THEN** the task fails and the error contains the reference

### Requirement: Structured output schema validation
An `llm_call` with `response_format: json` and an `output_schema` property SHALL validate its parsed
output against the schema and fail the task with the validation errors on mismatch.

#### Scenario: Non-conforming JSON
- **WHEN** the model returns JSON missing a required key
- **THEN** the task result is a failure listing the missing key

### Requirement: Subworkflow return shape
A `subworkflow` task with `expects` keys SHALL fail when the child's result lacks any listed key.

#### Scenario: Missing key
- **WHEN** `expects: [summary]` and the child output has no `summary`
- **THEN** the parent task fails naming `summary`

### Requirement: Library and built-ins are contract-clean
`WorkflowLibrary.save` SHALL refuse a definition with `error` findings, and every built-in workflow
SHALL have none.

#### Scenario: Built-ins
- **WHEN** all built-in workflows are loaded and validated
- **THEN** no `error` finding is returned

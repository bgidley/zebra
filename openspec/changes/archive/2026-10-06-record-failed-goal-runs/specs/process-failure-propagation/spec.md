## MODIFIED Requirements

### Requirement: Parent workflow execution reports child failure
`execute_goal_workflow` SHALL return a failed `TaskResult` whose error contains the child
process's `__error__` when the child process ends `FAILED`, unless the task's
`continue_on_failure` property is true. When `continue_on_failure` is true and the child fails,
times out, or execution raises, the action SHALL instead return a successful `TaskResult` whose
output (also stored under `output_key`) has `success: false` and `error` containing the failure.

#### Scenario: Child task fails
- **WHEN** `execute_goal_workflow` runs a child workflow whose task returns `TaskResult.fail("NameError: name 'fire_number' is not defined")`
- **THEN** the child process is `FAILED` and the action's result is a failure whose error contains `fire_number`

#### Scenario: Child task fails with continue_on_failure
- **WHEN** `execute_goal_workflow` with `continue_on_failure: true` runs a child workflow whose task returns `TaskResult.fail("NameError: name 'fire_number' is not defined")`
- **THEN** the child process is `FAILED`, the action's result is successful, and its output has `success: false` and an `error` containing `fire_number`

## ADDED Requirements

### Requirement: Propagate failure action
The `propagate_failure` action SHALL return `TaskResult.fail` with its resolved `error` property
(or `"Workflow execution failed"` when empty) when its resolved `success` property is false, and
SHALL succeed when it is true.

#### Scenario: Unsuccessful outcome
- **WHEN** `propagate_failure` runs with `success: "False"` and `error: "boom"`
- **THEN** it returns a failure with error `"boom"`

#### Scenario: Successful outcome
- **WHEN** `propagate_failure` runs with `success: "True"`
- **THEN** it returns success

### Requirement: Agent Main Loop records failed goal runs before failing
When the goal workflow run by the Agent Main Loop fails, the loop SHALL still run
`assess_and_record` (with `success` false and the child's error), `ethics_post_review` and
`update_conceptual_memory`, and the process SHALL then end `FAILED` with `__error__` containing the
child's error.

#### Scenario: Goal workflow fails
- **WHEN** the Agent Main Loop executes a goal workflow that fails with error `"boom"`
- **THEN** `assess_and_record` and `update_conceptual_memory` run with success false
- **AND** the main-loop process is `FAILED` with `__error__` containing `"boom"`

#### Scenario: Goal workflow succeeds
- **WHEN** the goal workflow succeeds
- **THEN** the main-loop process is `COMPLETE` with no `__error__`

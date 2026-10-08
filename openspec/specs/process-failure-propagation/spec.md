# process-failure-propagation Specification

## Purpose
How the engine propagates an unhandled task failure to its process: a process whose remaining tasks have finished with at least one FAILED task ends FAILED with the task's error recorded, never COMPLETE (#131).

## Requirements

### Requirement: Unhandled task failure fails the process
When a task transition leaves a process with no active tasks (none outside `COMPLETE`/`FAILED`)
and at least one task instance is `FAILED`, the engine SHALL mark the process `FAILED` (not
`COMPLETE`), set `completed_at`, set the `__error__` process property to the failed task's error
(or `"Task '<task definition id>' failed"` when it has none), and set `__failed_task__` to the
failed task's definition id. Tasks downstream of the failed task SHALL NOT run.

#### Scenario: Auto task returns a failure
- **WHEN** a serial workflow's auto task returns `TaskResult.fail("NameError: ...")` and has an outbound routing
- **THEN** the process is `FAILED` with `__error__` = `"NameError: ..."` and `__failed_task__` = that task's id
- **AND** the downstream task never runs

#### Scenario: Auto task raises
- **WHEN** an auto task's action raises `RuntimeError("boom")`
- **THEN** the process is `FAILED` with `__error__` = `"boom"`

#### Scenario: Failure after a human task is completed
- **WHEN** a human (`auto: false`) task is completed successfully via `complete_task` and the next auto task fails
- **THEN** the process is `FAILED` with the auto task's error

#### Scenario: Failure after recovery
- **WHEN** `resume_all_processes` runs while the process waits on a human task, and after the human task is completed the next auto task fails
- **THEN** the process is `FAILED` with the auto task's error

#### Scenario: Parallel branch fails while a sibling is still open
- **WHEN** one parallel branch's auto task fails while a sibling branch waits on a human task
- **THEN** the process stays `RUNNING` with no `__error__` until the sibling completes
- **AND** then the process is `FAILED` with the failed branch task's error

#### Scenario: Human task completed with a failure result
- **WHEN** a human task is completed via `complete_task` with `TaskResult.fail("user rejected")`
- **THEN** the process is `FAILED` with `__error__` = `"user rejected"`

### Requirement: Handled failures still complete
A task that signals a failure outcome by succeeding with a `next_route` SHALL be treated as
complete; its matching routing SHALL fire and the process SHALL complete normally without
`__error__`.

#### Scenario: Failure handled by conditional routing
- **WHEN** a task returns success with `next_route="failed"` routing to a recovery task that succeeds
- **THEN** the recovery task runs and the process is `COMPLETE` with no `__error__`

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

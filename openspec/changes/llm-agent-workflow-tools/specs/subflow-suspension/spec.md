## ADDED Requirements

### Requirement: Actions can suspend on child processes
A task action SHALL be able to return `TaskResult.suspend(children=[process_id, ...])`. The engine SHALL move the task to `AWAITING_SUBFLOW`, persist the pending child ids on the task, start every pending child still in `CREATED`, and SHALL NOT route the task onward while it is suspended.

#### Scenario: Suspend then resume
- **WHEN** an action suspends on one child process and that child completes
- **THEN** the engine re-runs the same task's action with `context.subflow_results` holding the child's `process_id`, `success`, `output` and `error`
- **AND** when that run returns a normal result the task completes and routes onward

#### Scenario: No polling while suspended
- **WHEN** a suspended task's child parks on a human task
- **THEN** `start_process` returns with the parent process `RUNNING` and the task `AWAITING_SUBFLOW`, and no coroutine waits on the child
- **AND** completing the human task completes the child and resumes the parent task

### Requirement: Resume waits for every child
A task suspended on several children SHALL resume only once all of them are terminal (`COMPLETE` or `FAILED`), and SHALL receive one result per child in the order the children were given.

#### Scenario: Parallel children
- **WHEN** a task suspends on two children and only the first has completed
- **THEN** the task stays `AWAITING_SUBFLOW`
- **AND** when the second completes the task resumes with two results

### Requirement: A failed child is a result, not a task failure
A child that ends `FAILED` SHALL be reported to the resumed action with `success: false` and the child's `__error__`; the engine SHALL NOT fail the suspended task because of it.

#### Scenario: Child fails
- **WHEN** a suspended task's only child fails
- **THEN** the task resumes and its action decides the outcome

### Requirement: Suspension survives restarts
The suspended state and pending child ids SHALL be persisted. Crash recovery SHALL leave `AWAITING_SUBFLOW` tasks suspended, start pending children that never left `CREATED`, and resume a suspended task whose children all finished while the engine was down.

#### Scenario: Children finished during downtime
- **WHEN** recovery runs and a suspended task's children are all terminal
- **THEN** the task is resumed and its process runs to completion

#### Scenario: Child never started
- **WHEN** recovery finds a suspended task with a pending child still `CREATED`
- **THEN** recovery starts the child, and the task resumes when it finishes

# subflow-suspension Specification

## Purpose
TBD - created by archiving change llm-agent-workflow-tools. Update Purpose after archive.

## Requirements

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

### Requirement: A suspended task resumes once
Only the caller that moves a task from `AWAITING_SUBFLOW` to `READY` SHALL run it, so children that finish at the same time resume the task exactly once.

#### Scenario: Children finish together
- **WHEN** both children of a suspended task are completed concurrently
- **THEN** the task's action is re-run once, with both results

### Requirement: Failing a parent fails its waiting children
When a process is failed, the engine SHALL fail every non-terminal child process linked to it by `parent_process_id`, whether or not one of its suspended tasks was waiting on it, with an error naming the parent.

#### Scenario: Goal cancelled during a tool call
- **WHEN** a process is failed while its task waits on a child parked on a human task
- **THEN** the child process is failed and its human task is no longer pending

#### Scenario: Linked child no task waits on
- **WHEN** a process is failed while a child linked by `parent_process_id` is parked on a human task and none of the parent's tasks is suspended on it
- **THEN** the child process is failed with "Parent process <id> failed: <reason>" and its human task is no longer pending

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

### Requirement: A finished child resumes every task waiting on it
When a child process becomes COMPLETE or FAILED, the engine SHALL check for resume every
AWAITING_SUBFLOW task of the child's parent process that lists the child among its pending
subflows, as well as the child's `parent_task_id`.

#### Scenario: Waiting task is not the spawning task
- **WHEN** task A spawns a child and completes, and task B of the same process suspends on that child
- **THEN** B resumes when the child finishes

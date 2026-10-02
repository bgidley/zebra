# goal-crash-recovery Specification

## Purpose
TBD - created by archiving change resumable-goal-execution. Update Purpose after archive.

## Requirements

### Requirement: Goal workflow execution re-attaches to its existing child
The `execute_goal_workflow` action SHALL record the id of the child process it spawns on its task
(`__child_process_id__`) before starting the child. When the action runs for a task that already
records a child still linked to the same parent process and task, it SHALL wait on that child
instead of creating a new one, starting it first if it is still CREATED.

#### Scenario: Re-run while the child is still running
- **WHEN** the action re-runs for a task whose recorded child is RUNNING
- **THEN** no new child process is created and the action returns the child's result once it completes

#### Scenario: Re-run after the child already finished
- **WHEN** the action re-runs for a task whose recorded child is COMPLETE
- **THEN** the action returns the child's output immediately without creating a new child

#### Scenario: Recorded child is not linked to this task
- **WHEN** the recorded child's `parent_process_id` or `parent_task_id` does not match the task
- **THEN** the action spawns a new linked child and records its id on the task

### Requirement: Interrupted goals are recovered without duplicate work
The Agent Main Loop's `execute_workflow` task SHALL be declared idempotent so that crash recovery
resets it to READY and re-drives it. `resume_all_processes` SHALL recover child processes before
their parents.

#### Scenario: Goal driver killed mid-execution
- **WHEN** the driver of a goal is killed while `execute_workflow` waits on its child, and recovery runs
- **THEN** the goal process completes with the child's output and exactly one child process exists

#### Scenario: Children recovered first
- **WHEN** a parent, its child and its grandchild are all RUNNING at recovery
- **THEN** they are recovered in the order grandchild, child, parent

### Requirement: Startup recovery does not block the daemon
The daemon SHALL run startup recovery as a background task so the scheduler loop starts without
waiting for recovered goals to finish, and SHALL cancel unfinished recovery when it stops.
Recovery errors SHALL be logged and never stop the daemon.

#### Scenario: Long recovered goal
- **WHEN** recovery is still re-driving a goal
- **THEN** the scheduler loop is already running

#### Scenario: Recovery fails
- **WHEN** `resume_all_processes` raises
- **THEN** the error is logged and the daemon keeps running

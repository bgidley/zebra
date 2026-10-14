## MODIFIED Requirements

### Requirement: Goal workflow execution re-attaches to its existing child
The `execute_goal_workflow` action SHALL record the id of the child process it spawns on its task
(`__child_process_id__`) before starting the child. When the action runs for a task that already
records a child still linked to the same parent process and task, it SHALL suspend on that child
instead of creating a new one, starting it first if it is still CREATED.

#### Scenario: Re-run while the child is still running
- **WHEN** the action re-runs for a task whose recorded child is RUNNING
- **THEN** no new child process is created and the action suspends on that child

#### Scenario: Re-run after the child already finished
- **WHEN** the action re-runs for a task whose recorded child is COMPLETE
- **THEN** no new child is created, and on resume the action returns the child's output

#### Scenario: Recorded child is not linked to this task
- **WHEN** the recorded child's `parent_process_id` or `parent_task_id` does not match the task
- **THEN** the action spawns a new linked child, records its id on the task and suspends on it

### Requirement: Interrupted goals are recovered without duplicate work
The Agent Main Loop's `execute_workflow` task SHALL be declared idempotent so that crash recovery
resets it to READY and re-drives it. `resume_all_processes` SHALL recover child processes before
their parents. A goal whose task is suspended on its child is not interrupted by a restart.

#### Scenario: Goal driver killed mid-execution
- **WHEN** the driver of a goal is killed while `execute_workflow` is running, and recovery runs
- **THEN** the task re-attaches to its child and, once the child completes, the goal process completes with the child's output and exactly one child process exists

#### Scenario: Restarts while waiting on a human
- **WHEN** recovery runs repeatedly while the goal's `execute_workflow` task is suspended on a child parked on a human task
- **THEN** the task stays AWAITING_SUBFLOW, its `execution_attempt` is unchanged and the goal is not failed

#### Scenario: Children recovered first
- **WHEN** a parent, its child and its grandchild are all RUNNING at recovery
- **THEN** they are recovered in the order grandchild, child, parent

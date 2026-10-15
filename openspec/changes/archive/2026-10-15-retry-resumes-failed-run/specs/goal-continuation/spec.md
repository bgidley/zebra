## ADDED Requirements

### Requirement: Retrying a failed run resumes where it stopped

When the continuation assessor chooses `same_workflow` for a previous run that failed in that
same workflow, `execute_goal_workflow` SHALL start the new goal-workflow process at the tasks the
failed process never completed, with the failed process's workflow properties and completed task
outputs carried over, so answered human tasks are not asked again. The new process SHALL record
`__resumed_from__` with the failed process id and the start task ids. In every other case the
workflow SHALL start at its first task.

#### Scenario: Retry after the last step failed

- **WHEN** a run's goal workflow failed on an auto task after the user answered its forms, and the user continues it with "Retry" and the assessor chooses `same_workflow`
- **THEN** the new goal workflow starts at the failed task, no form is asked again, completed tasks are not re-run, and the answers are available to the resumed task

#### Scenario: Previous run succeeded or another workflow chosen

- **WHEN** the previous run succeeded, or the assessor chooses `existing_workflow` or `new_workflow`
- **THEN** the goal workflow starts at its first task

#### Scenario: Workflow changed since the failure

- **WHEN** a task the failed process had not completed no longer exists in the workflow definition, or is a synchronized join
- **THEN** the goal workflow starts at its first task

#### Scenario: Retry of a retry

- **WHEN** a resumed run fails again and is retried
- **THEN** the new goal workflow resumes from the latest failed attempt

### Requirement: Processes can start at given tasks

`WorkflowEngine.start_process` and `start_process_with_timeout` SHALL accept optional
`start_task_ids`. When given, the process SHALL start with one task per id, each on its own flow
of execution, instead of the definition's first task; an unknown id SHALL raise.

#### Scenario: Start at a later task

- **WHEN** a process is started with `start_task_ids` naming its second auto task
- **THEN** only that task and its successors run

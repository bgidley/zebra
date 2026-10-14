## ADDED Requirements

### Requirement: Engine journals each lifecycle step
The engine SHALL append a `ProcessEvent` when a process starts, completes or fails, and when a task becomes available for a human, starts, suspends on subflows, completes or fails. Each event SHALL record the process id, the task instance and definition ids (for task events), the attempt, a timestamp and any error.

#### Scenario: Serial workflow
- **WHEN** a two-task auto workflow runs to completion
- **THEN** its journal holds process_started, task_started and task_completed for each task, then process_completed, in that order

#### Scenario: Failed task
- **WHEN** a task fails and the process fails with it
- **THEN** the task_failed and process_failed events both carry the error

### Requirement: Events carry property diffs that replay exactly
Each event SHALL carry the process properties set or changed, and the keys removed, since the previous event for that process. Replaying a process's events in order SHALL rebuild its properties after any event; after the last event they SHALL equal the stored process properties. Values whose JSON exceeds 16,000 characters SHALL be stored as a truncated preview.

#### Scenario: Replay matches final properties
- **WHEN** a process completes
- **THEN** replaying its events yields its stored properties

#### Scenario: Engine restart
- **WHEN** a different engine instance completes a human task on a process it never journalled
- **THEN** the completion event holds only the task's output, not every property again

### Requirement: Journal never fails a workflow
A failure to write a journal event SHALL be logged and SHALL NOT change the outcome of the workflow.

#### Scenario: Store rejects events
- **WHEN** `save_process_event` raises
- **THEN** the workflow still completes

### Requirement: Stores expose the journal and subflows
`StateStore` SHALL provide `save_process_event`, `load_process_events(process_ids)` ordered by time, and `list_child_processes(parent_process_id)`. Deleting a process SHALL delete its events. Stores SHALL persist a parent link set on a process after it was first saved.

#### Scenario: Child listed under its parent
- **WHEN** a spawner sets `parent_process_id` and `parent_task_id` on a saved child and saves it again
- **THEN** `list_child_processes(parent)` returns the child with that `parent_task_id`

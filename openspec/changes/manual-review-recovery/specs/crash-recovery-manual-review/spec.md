## ADDED Requirements

### Requirement: Flagged tasks can be retried
The engine SHALL provide `retry_task(task_id)` that, for a task in RUNNING state carrying
`__requires_manual_review__` whose process is RUNNING, removes the flag, moves the task to READY
and runs the process's pending auto tasks. Any other task or process state SHALL raise
`InvalidStateTransitionError` without changing state.

#### Scenario: Retry re-runs the task
- **WHEN** recovery flagged an interrupted task and `retry_task` is called
- **THEN** the flag is removed, the task's action runs again and the process continues to completion

#### Scenario: Unflagged task is rejected
- **WHEN** `retry_task` is called for a RUNNING task without the flag
- **THEN** `InvalidStateTransitionError` is raised

### Requirement: Recovery gives up after repeated interruptions
`resume_all_processes(max_interrupted_attempts=N)` SHALL fail the owning process, with an
`__error__` naming the task and the interruption count, when a RUNNING task's `execution_attempt`
reaches N, instead of resetting or flagging it again. With no cap the previous behaviour is kept.
The daemon SHALL pass `RECOVERY_MAX_INTERRUPTED_ATTEMPTS` (default 3).

#### Scenario: Third interruption fails the run
- **WHEN** a task is found RUNNING by recovery for the 3rd time with a cap of 3
- **THEN** its process is FAILED and `__error__` says the task was interrupted 3 times

#### Scenario: No cap keeps flagging
- **WHEN** recovery runs repeatedly without a cap
- **THEN** the task stays RUNNING and flagged and its process stays RUNNING

### Requirement: Flagged tasks are surfaced with Retry and Fail controls
The activity page and run detail page SHALL list tasks awaiting manual review for running goals,
each with Retry and Fail buttons. Retry SHALL reset the task immediately and re-run it in the
background. Fail SHALL fail the task's process and every non-terminal ancestor process.

#### Scenario: Activity shows a flagged task
- **WHEN** a running goal has a flagged task
- **THEN** `/activity/` shows "review needed" with Retry and Fail actions for that task

#### Scenario: Fail ends the whole run
- **WHEN** Fail is pressed for a flagged task in a child process
- **THEN** the child and its parent process are FAILED

### Requirement: REST endpoints for manual review
The API SHALL expose `GET /api/review-tasks/` (optional `run_id` filter),
`POST /api/tasks/<id>/retry/` (202) and `POST /api/tasks/<id>/fail/` (optional `reason` stored as
`__error__`), authenticated like the other API endpoints. Unknown tasks SHALL return 404 and tasks
not awaiting review SHALL return 409.

#### Scenario: Retry via API
- **WHEN** an authenticated client POSTs to `/api/tasks/<id>/retry/` for a flagged task
- **THEN** the response is 202 with state "ready"

#### Scenario: Unauthenticated request
- **WHEN** an unauthenticated client POSTs to `/api/tasks/<id>/retry/`
- **THEN** the request is rejected and the task is not retried

## ADDED Requirements

### Requirement: A finished child resumes every task waiting on it
When a child process becomes COMPLETE or FAILED, the engine SHALL check for resume every
AWAITING_SUBFLOW task of the child's parent process that lists the child among its pending
subflows, as well as the child's `parent_task_id`.

#### Scenario: Waiting task is not the spawning task
- **WHEN** task A spawns a child and completes, and task B of the same process suspends on that child
- **THEN** B resumes when the child finishes

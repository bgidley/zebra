## MODIFIED Requirements

### Requirement: Failing a parent fails its waiting children
When a process is failed, the engine SHALL fail every non-terminal child process linked to it by `parent_process_id`, whether or not one of its suspended tasks was waiting on it, with an error naming the parent.

#### Scenario: Goal cancelled during a tool call
- **WHEN** a process is failed while its task waits on a child parked on a human task
- **THEN** the child process is failed and its human task is no longer pending

#### Scenario: Linked child no task waits on
- **WHEN** a process is failed while a child linked by `parent_process_id` is parked on a human task and none of the parent's tasks is suspended on it
- **THEN** the child process is failed with "Parent process <id> failed: <reason>" and its human task is no longer pending

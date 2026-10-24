## ADDED Requirements

### Requirement: Child processes are linked from creation
Every action that runs a workflow as a child process (`execute_goal_workflow`, `subworkflow`,
`parallel_subworkflows`) SHALL create the child already linked to its parent process and task,
so the child is never stored as a top-level CREATED process. The goal queue SHALL therefore
never offer a child process as a goal, and each child SHALL be started exactly once (#227).

#### Scenario: Goal workflow child is never queued
- **WHEN** `execute_goal_workflow` creates its child process
- **THEN** the child's first stored state already has `parent_process_id` and `parent_task_id`, and the goal queue's pending goals never include it

#### Scenario: Subworkflow children are never queued
- **WHEN** `subworkflow` or `parallel_subworkflows` creates a child process
- **THEN** the child's first stored state already has its parent link, and the goal queue's pending goals never include it

#### Scenario: Child started once
- **WHEN** a goal runs its workflow as a child process
- **THEN** the child's step journal has exactly one `process_started` event

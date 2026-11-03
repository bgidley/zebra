## ADDED Requirements

### Requirement: Stamped and legacy workflows run
A workflow saved through the library (with a `commons` block) and a workflow file without a block
SHALL both be offered to the workflow selector and run to completion when selected.

#### Scenario: Stamped workflow runs
- **WHEN** a workflow saved with `add_workflow` is picked by `workflow_selector`
- **THEN** `execute_goal_workflow` runs it to completion and the goal process completes

#### Scenario: Legacy workflow runs
- **WHEN** a blockless workflow file is picked by `workflow_selector`
- **THEN** `execute_goal_workflow` runs it to completion and the goal process completes

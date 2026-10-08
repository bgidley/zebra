## MODIFIED Requirements

### Requirement: Generated workflows must be structurally valid
Workflow generator actions SHALL run `validate_definition` on the parsed definition and SHALL fail without saving the workflow when it reports errors. The `workflow_creator` action SHALL first make one repair attempt, sending the parse or validation error back to the LLM, and SHALL fail only if the repaired YAML is still invalid. Truncated output SHALL NOT be repaired.

#### Scenario: Generated workflow has an orphaned task
- **WHEN** the generated YAML parses but a non-first task has no incoming routing, and the repair attempt is also invalid
- **THEN** the task fails with the validation error
- **AND** the workflow is not added to the library and `workflow_name` is not set

#### Scenario: Repair fixes an invalid workflow
- **WHEN** the first generated YAML is invalid and the repair attempt returns a valid workflow
- **THEN** the repaired workflow is saved to the library and selected for execution

#### Scenario: Generated workflow is valid
- **WHEN** the generated YAML is complete and every task is reachable
- **THEN** the workflow is saved to the library and selected for execution

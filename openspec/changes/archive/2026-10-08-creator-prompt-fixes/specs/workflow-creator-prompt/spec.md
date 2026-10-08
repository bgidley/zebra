## ADDED Requirements

### Requirement: Top-level result_key is honoured
The definition loader SHALL copy a top-level `result_key` into `ProcessDefinition.properties["result_key"]`. When `properties.result_key` is also set, the explicit `properties` value SHALL win.

#### Scenario: Top-level result_key
- **WHEN** a workflow YAML declares `result_key: summary` at the top level
- **THEN** the loaded definition's `properties["result_key"]` is `summary`

#### Scenario: Both forms present
- **WHEN** a YAML declares top-level `result_key: a` and `properties: {result_key: b}`
- **THEN** `properties["result_key"]` is `b`

### Requirement: Generated route_name routings must be reachable
`check_generated_workflow` SHALL reject a generated workflow that has a `condition: route_name` routing whose source task uses the `llm_call` action, since `llm_call` never sets `next_route`.

#### Scenario: route_name after llm_call
- **WHEN** a generated workflow routes from an `llm_call` task with `condition: route_name`
- **THEN** the workflow is rejected with an error naming the routing's source task

### Requirement: Creator prompt describes engine semantics
The `workflow_creator` system prompt SHALL explain: how values are referenced (`{{output_key}}` for an action's main value, `{{__task_output_<task_id>.<field>}}` for its full Outputs and for human form fields); that serial routings stop at the first that fires; `parallel: true` fan-out and `synchronized: true` joins; that `condition: route_name` routes are chosen only by human tasks, whose route names appear as buttons; and that file-modifying or code-executing actions should be used only when the goal requires them.

#### Scenario: Prompt content
- **WHEN** the creator builds its system prompt
- **THEN** it contains guidance on `{{__task_output_<task_id>.<field>}}`, `parallel: true`, `synchronized: true`, route-name buttons and side-effecting actions
- **AND** it does not tell the LLM to use an enum field to drive routing

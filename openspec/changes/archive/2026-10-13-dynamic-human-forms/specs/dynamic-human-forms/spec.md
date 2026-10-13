## ADDED Requirements

### Requirement: Human task schema may reference a generated schema
A human task's `properties.schema` SHALL accept either a JSON Schema object or a string that is exactly one `{{reference}}` (`{{key}}`, `{{key.field}}` or `{{task_id.output}}`). The reference SHALL be resolved against the process properties to a JSON Schema object. The resolved value may be a dict, a JSON string (optionally fenced) or a task output wrapping either under `response`. A value without a non-empty `properties` object SHALL resolve to no schema.

#### Scenario: One field per generated question
- **WHEN** a human task has `schema: "{{followup_form}}"` and `followup_form` holds a JSON Schema with properties `venues` and `paddle_feather`
- **THEN** the task form renders a `venues` field and a `paddle_feather` field, titled with the questions

#### Scenario: Unresolvable reference
- **WHEN** the referenced property is missing or is not a JSON Schema object
- **THEN** the form renders the single `response` fallback field

#### Scenario: Static schema unchanged
- **WHEN** a human task's schema is a JSON Schema object
- **THEN** it is rendered and validated exactly as before

### Requirement: Generated schema is used everywhere a task schema is read
The web form, web submit, pending-task lists, the task-complete API, the pending-tasks API and `execute_goal_workflow`'s `user_inputs` SHALL use the resolved schema.

#### Scenario: Submit validates against the generated schema
- **WHEN** a user submits a generated-schema form without a field the generated schema marks required
- **THEN** the form is re-rendered with a required-field error and the task stays READY

#### Scenario: API validates against the generated schema
- **WHEN** `POST /api/tasks/<id>/complete/` omits a field the generated schema requires
- **THEN** the response is 400

#### Scenario: Generated schema is not shown as a prior output
- **WHEN** the task that produced the generated schema has its output in the process properties
- **THEN** the form page does not list that schema among the prior task outputs

### Requirement: Workflow creator generates follow-up forms
The `workflow_creator` system prompt SHALL describe generating a form with `llm_call` + `response_format: json` and referencing it with `schema: "{{output_key}}"`. `check_generated_workflow` SHALL reject a generated workflow whose task `schema` is a string that is not a single reference.

#### Scenario: Prose schema string rejected
- **WHEN** a generated workflow has `schema: "Answer these: {{questions}}"`
- **THEN** the workflow is rejected with an error naming the task

#### Scenario: Reference accepted
- **WHEN** a generated workflow has `schema: "{{form}}"`
- **THEN** the workflow is accepted

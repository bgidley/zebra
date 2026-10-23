## ADDED Requirements

### Requirement: Continuations expose the previous run's outputs
When `execute_goal_workflow` starts the goal workflow for a goal whose `previous_run_context` names a run, it SHALL look up that run's goal-workflow process (completed or failed) and SHALL pass its workflow properties to the new child process as the `prior_outputs` dict. It SHALL leave out keys starting with `__`, `goal` and `prior_outputs`. A string value longer than 8000 characters SHALL be cut to 8000; any other value whose JSON is longer than 8000 characters SHALL be dropped; a value that would take the dict's total size past 32000 characters SHALL be left out. When the previous process cannot be found, the goal workflow SHALL start without `prior_outputs` and a warning SHALL be logged.

#### Scenario: Prior output reachable from a template
- **WHEN** a goal continues run *A*, whose goal workflow set `research_brief`, and the new workflow's task prompt is `{{prior_outputs.research_brief}}`
- **THEN** the task's prompt resolves to *A*'s research brief

#### Scenario: Not a continuation
- **WHEN** a goal has no `previous_run_context`
- **THEN** the goal workflow has no `prior_outputs` property

#### Scenario: Internal and oversized values left out
- **WHEN** the previous goal workflow has `__task_output_x`, `goal`, `prior_outputs`, a 20000-character string and a list whose JSON is 20000 characters
- **THEN** `prior_outputs` has none of the first three, the string is cut to 8000 characters and the list is absent

#### Scenario: Previous process missing
- **WHEN** a goal's `previous_run_context` names a run with no stored process
- **THEN** the goal workflow starts without `prior_outputs` and a warning is logged

### Requirement: Inputs bind to prior outputs with from_prior
An input in a workflow's `inputs` schema MAY declare `from_prior: <key>`. When the goal workflow starts with `prior_outputs` containing `<key>`, the input SHALL be set to that value, unless the child's properties already set it. Without `prior_outputs`, or without that key, the input SHALL be left unset.

#### Scenario: Input bound from the previous run
- **WHEN** a continuation runs a workflow declaring `prior_brief: {type: string, from_prior: research_brief}` and the previous run set `research_brief`
- **THEN** the child's `prior_brief` property is the previous research brief

#### Scenario: Key missing in the previous run
- **WHEN** the previous run did not set `research_brief`
- **THEN** the child has no `prior_brief` property

### Requirement: Workflow authors are told about prior outputs
The workflow creator's and optimizer's prompts SHALL say that on a continuation `{{prior_outputs.<key>}}` holds the previous run's value of an output key and that an input can declare `from_prior: <key>`.

#### Scenario: Prompts mention prior outputs
- **WHEN** the creator or optimizer builds its prompt
- **THEN** the prompt mentions `prior_outputs` and `from_prior`

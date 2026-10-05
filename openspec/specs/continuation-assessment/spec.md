# continuation-assessment Specification

## Purpose
Before a continued goal runs, decide whether to reuse the previous workflow, pick another library workflow, or create a new one, and record that decision and its rationale on the run (F135, #135).

## Requirements

### Requirement: Continuation goals are assessed before workflow selection
The agent main loop SHALL run the `continuation_assessor` action after the ethics input gate approves and before workflow selection or creation. When the process has a `previous_run_context` property, the assessor SHALL ask the LLM to choose one of `same_workflow`, `existing_workflow` or `new_workflow` and SHALL return that choice as `next_route`. The LLM sees the previous run's goal, workflow, success, output and task progress (when present), plus the `continuation_comment` property (when set).

#### Scenario: Same workflow chosen
- **WHEN** a continuation's LLM assessment returns `same_workflow` and the previous workflow is in the library
- **THEN** the assessor routes `same_workflow`, sets `workflow_name` to the previous workflow, and the loop continues to concern flagging without running the selector

#### Scenario: Existing workflow chosen
- **WHEN** a continuation's LLM assessment returns `existing_workflow`
- **THEN** the loop runs the existing workflow selector

#### Scenario: New workflow chosen
- **WHEN** a continuation's LLM assessment returns `new_workflow`
- **THEN** the loop runs the existing workflow creator, with its YAML validation safeguards

### Requirement: Non-continuation goals are unaffected
When the process has no `previous_run_context`, the assessor SHALL route `not_continuation` to the workflow selector without calling the LLM and without setting any continuation properties.

#### Scenario: Fresh goal
- **WHEN** a goal without `previous_run_context` passes the ethics input gate
- **THEN** no LLM call is made, `continuation_decision` stays unset, and the selector runs as before

### Requirement: Assessment degrades gracefully
The assessor SHALL route `existing_workflow` and log a warning when the LLM provider is unavailable, the LLM call fails, or the response cannot be parsed into a known decision. A `same_workflow` decision whose workflow is no longer in the library SHALL also fall back to `existing_workflow`.

#### Scenario: LLM failure
- **WHEN** the LLM call raises or returns invalid JSON
- **THEN** the assessor routes `existing_workflow` and records a rationale that explains the fallback

#### Scenario: Previous workflow deleted
- **WHEN** the LLM chooses `same_workflow` but the previous workflow is no longer in the library
- **THEN** the assessor routes `existing_workflow`

### Requirement: Decision is persisted and visible
The assessor SHALL set the `continuation_decision` and `continuation_rationale` process properties to the route taken and its rationale. These SHALL be stored on the `WorkflowRun` and shown on the run detail page.

#### Scenario: Run page shows the decision
- **WHEN** a run has a `continuation_decision`
- **THEN** the run detail page shows the decision and its rationale

## ADDED Requirements

### Requirement: A failed goal run asks a human for help
When the Agent Main Loop's goal workflow fails and fewer than `max_help_requests` help requests
have been made for the goal, the loop SHALL park on the `stuck_help_request` human task instead of
proceeding to record and fail. The task SHALL show the goal and a help request stating what was
tried, where it is stuck and what is needed.

#### Scenario: Goal workflow fails for the first time
- **WHEN** `execute_workflow` completes with `success: false`
- **THEN** the process stays RUNNING with a READY `stuck_help_request` task, and `help_request_display` describes the attempt and the error

#### Scenario: No LLM available to write the request
- **WHEN** the help request is prepared and no LLM provider can be used
- **THEN** a plain help request is built from the goal, workflow and error and the goal still parks

#### Scenario: Successful run
- **WHEN** `execute_workflow` completes with `success: true`
- **THEN** no help request is made and the loop proceeds to assess and record

### Requirement: The help budget is bounded
The loop SHALL count help requests per goal and SHALL NOT ask again once `max_help_requests`
(default 2) have been made; the failure is then recorded and the process ends FAILED as before.

#### Scenario: Budget spent
- **WHEN** the goal workflow fails after `max_help_requests` help requests were already made
- **THEN** no human task is created and the process ends FAILED with the goal workflow's error

### Requirement: The goal resumes with the human's answer
`apply_help_response` SHALL route on the human's decision: `retry` re-runs the same workflow with
the human's guidance and the previous error added to the executed goal; `redirect` replaces the
goal with the human's text and goes back through the ethics input gate and workflow selection;
`abandon` records the failure, noting it was abandoned, and ends FAILED.

#### Scenario: Retry with guidance succeeds
- **WHEN** the human chooses `retry` with guidance and the second run succeeds
- **THEN** the child goal contains the guidance and previous error, and the process completes

#### Scenario: Redirect
- **WHEN** the human chooses `redirect` with a new goal
- **THEN** `goal` becomes the new text, `original_goal` keeps the old one, and the input gate runs again

#### Scenario: Abandon
- **WHEN** the human chooses `abandon`
- **THEN** assess/learn run with the failure and the process ends FAILED with an error noting it was abandoned

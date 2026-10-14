## MODIFIED Requirements

### Requirement: Goal workflow timeout enforced
`execute_goal_workflow` SHALL bound the child workflow's inline run by its `timeout` property and report a timeout as a failed execution, including the cost and tokens the child had already spent.

#### Scenario: Slow goal workflow
- **WHEN** the child workflow runs longer than `timeout`
- **THEN** the child process is FAILED and the action fails with an error containing "Timed out after"

#### Scenario: Hang after a human task
- **WHEN** the child has spent on LLM calls, parks on a human task, and after the submit an auto task fails (e.g. an LLM call hits `ZEBRA_LLM_TIMEOUT_SECONDS`)
- **THEN** the goal's task stays suspended until the child is FAILED, then resumes and reports the child's error with its `cost`, `tokens_used`, `input_tokens` and `output_tokens`; the parent does not time the child out itself

## ADDED Requirements

### Requirement: Human wait in the goal workflow is not timed out
`execute_goal_workflow` SHALL suspend its task on the child workflow instead of waiting inline, so a goal whose child parks on a human task returns from its bounded run and the goal timeout does not count the human's time.

#### Scenario: Child parks on a human task
- **WHEN** a goal is run with a goal timeout and its child workflow parks on a human task
- **THEN** the bounded run returns before the timeout, the goal stays RUNNING with its `execute_workflow` task AWAITING_SUBFLOW, and it is still RUNNING after the timeout has elapsed

#### Scenario: Human answers after the goal timeout
- **WHEN** the human completes the child's task after the goal timeout has elapsed
- **THEN** the goal resumes and its `execution_result` carries the child's output, `cost`, `tokens_used`, `input_tokens`, `output_tokens` and `user_inputs`

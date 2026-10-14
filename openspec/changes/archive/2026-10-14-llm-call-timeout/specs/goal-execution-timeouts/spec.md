## MODIFIED Requirements

### Requirement: Goal workflow timeout enforced
`execute_goal_workflow` SHALL bound the child workflow's inline run by its `timeout` property and report a timeout as a failed execution. When its wait for the child times out (including a chain resumed by a human-task submit), it SHALL fail the child process and report the cost and tokens the child had already spent.

#### Scenario: Slow goal workflow
- **WHEN** the child workflow runs longer than `timeout`
- **THEN** the child process is FAILED and the action fails with an error containing "Timed out after"

#### Scenario: Hang after a human task
- **WHEN** the child has spent on LLM calls, parks on a human task, and after the submit an auto task runs longer than `timeout`
- **THEN** the action fails with "Timeout after <timeout>s", the child process is FAILED with that error, and the result reports the child's `cost`, `tokens_used`, `input_tokens` and `output_tokens`

## ADDED Requirements

### Requirement: Bounded LLM API attempts
Every LLM provider SHALL bound each API attempt by `ZEBRA_LLM_TIMEOUT_SECONDS` (default 180s; invalid or non-positive values fall back to the default) with at most 2 retries, so a stalled request fails within a 600s goal budget.

#### Scenario: Default timeout
- **WHEN** a provider is created without `ZEBRA_LLM_TIMEOUT_SECONDS` set
- **THEN** its client timeout is 180s with 2 retries

#### Scenario: Override
- **WHEN** `ZEBRA_LLM_TIMEOUT_SECONDS=90`
- **THEN** the Anthropic, OpenAI, OpenRouter and Kimi clients use a 90s timeout

### Requirement: Late results on failed processes are discarded
When a process is failed while one of its actions is running, the engine SHALL discard that action's result when it returns: no output stored, no routing, and the process stays FAILED.

#### Scenario: Process failed mid-action
- **WHEN** `fail_process` is called while an auto task's action is running and the action then succeeds
- **THEN** the process remains FAILED with its original error, the task remains FAILED, and no successor task is created

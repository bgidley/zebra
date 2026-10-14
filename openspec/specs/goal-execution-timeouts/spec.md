# goal-execution-timeouts Specification

## Purpose
Bound goal execution in time. `start_process` runs auto tasks inline, so goal runs (daemon, `AgentLoop`, child goal workflows) start through `start_process_with_timeout`, which fails a hung or slow chain at its deadline and lets the kill switch cancel it mid-run (#142).

## Requirements

### Requirement: Bounded process start
The engine SHALL provide `start_process_with_timeout` that runs a process's inline auto-task chain with a time bound, and SHALL fail the process when the bound is exceeded.

#### Scenario: Chain finishes in time
- **WHEN** a process's auto tasks complete before the timeout
- **THEN** the process is returned COMPLETE, unchanged in behaviour from `start_process`

#### Scenario: Chain exceeds timeout
- **WHEN** an auto task is still running when the timeout elapses
- **THEN** the chain is cancelled, all non-terminal tasks are FAILED, the process is FAILED with `__error__` "Timed out after <timeout>s", and the process lock is released

#### Scenario: Cancel check requests cancellation
- **WHEN** the supplied `cancel_check` returns a reason while the chain is running
- **THEN** the chain is cancelled and the process is FAILED with that reason

#### Scenario: Caller is cancelled
- **WHEN** the awaiting caller is cancelled
- **THEN** the chain is cancelled, the process is FAILED with "Cancelled by caller", and the cancellation propagates

#### Scenario: Manual task pause
- **WHEN** the chain parks on a manual (`auto: false`) task before the timeout
- **THEN** the call returns the RUNNING process and later elapsed time does not fail it

### Requirement: Goal workflow timeout enforced
`execute_goal_workflow` SHALL bound the child workflow's inline run by its `timeout` property and report a timeout as a failed execution. When its wait for the child times out (including a chain resumed by a human-task submit), it SHALL fail the child process and report the cost and tokens the child had already spent.

#### Scenario: Slow goal workflow
- **WHEN** the child workflow runs longer than `timeout`
- **THEN** the child process is FAILED and the action fails with an error containing "Timed out after"

#### Scenario: Hang after a human task
- **WHEN** the child has spent on LLM calls, parks on a human task, and after the submit an auto task runs longer than `timeout`
- **THEN** the action fails with "Timeout after <timeout>s", the child process is FAILED with that error, and the result reports the child's `cost`, `tokens_used`, `input_tokens` and `output_tokens`

### Requirement: Goal run timeout and kill switch
`AgentLoop.process_goal` and the daemon SHALL bound a goal's inline run by the configured goal timeout (`goal_timeout` / `GOAL_TIMEOUT_SECONDS`, default 900s), and the daemon SHALL cancel an in-flight goal when the kill switch is set.

#### Scenario: Slow goal via process_goal
- **WHEN** a goal's auto tasks run longer than `goal_timeout`
- **THEN** `process_goal` returns promptly with `success=False` and an error containing "Timed out after"

#### Scenario: Slow goal in the daemon
- **WHEN** the daemon runs a goal whose auto tasks exceed `GOAL_TIMEOUT_SECONDS`
- **THEN** the daemon tick returns and the goal's process is FAILED

#### Scenario: Kill switch mid-run
- **WHEN** the kill switch is set while a goal's auto tasks are running
- **THEN** the daemon cancels the run and the process is FAILED with "Kill switch activated"

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

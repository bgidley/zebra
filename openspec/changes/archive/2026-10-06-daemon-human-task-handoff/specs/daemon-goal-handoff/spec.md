## ADDED Requirements

### Requirement: Daemon hands off goals waiting on a human
The budget daemon SHALL run each picked goal in a background task and SHALL stop waiting on it as soon as the goal, or any running descendant process, has a READY task whose definition is `auto: false`. The goal SHALL remain tracked and the next tick SHALL be free to pick another queued goal.

#### Scenario: Ethics dilemma does not block the queue
- **WHEN** the daemon starts a goal that pauses on the `ethics_dilemma_resolution` human task
- **THEN** `_tick` returns without waiting for the human, and the next tick starts the next queued goal

#### Scenario: Human task in the executed child workflow does not block the queue
- **WHEN** the goal's child workflow pauses on an `auto: false` task while `start_process` is still running
- **THEN** `_tick` returns and the goal remains tracked with its execution task still running

#### Scenario: Auto-only goal finishes within the tick
- **WHEN** the daemon picks a goal whose workflow has no human tasks
- **THEN** the process is COMPLETE when `_tick` returns

### Requirement: Daemon reconciles in-flight goals
On every tick the daemon SHALL check each tracked goal and, for any that reached COMPLETE or FAILED, SHALL log the outcome with cost and increment `goals_completed` with status `success` or `failed`, then stop tracking it. Goals the daemon starts SHALL be marked with the `__daemon_started__` process property, and after a daemon restart the tracker SHALL resume tracking RUNNING top-level processes carrying that marker.

#### Scenario: Goal finished after a human answered is recorded
- **WHEN** a goal handed off on a human task later completes
- **THEN** the next tick logs `[daemon:done]` with its cost and increments `goals_completed{status="success"}` exactly once

#### Scenario: Restart keeps tracking a parked goal
- **WHEN** the daemon restarts while a daemon-started goal is RUNNING and waiting on a human
- **THEN** the new daemon tracks it and records its outcome when it terminates

### Requirement: Serial execution of active goals
The daemon SHALL NOT pick a new goal while a tracked goal's execution task is still running and the goal is not waiting on a human.

#### Scenario: Resumed goal blocks pickup
- **WHEN** a tracked goal's execution task is running and no human task is pending
- **THEN** the tick does not call `pick_next`

### Requirement: Kill switch cancels an executing goal
When the kill switch is active, the daemon SHALL cancel the background execution task of every tracked goal that is not waiting on a human, and SHALL mark its process FAILED with reason "Kill switch activated".

#### Scenario: Halt during execution
- **WHEN** the kill switch is set while a goal's execution task is running
- **THEN** the task is cancelled and the process is FAILED with `__error__ == "Kill switch activated"`

### Requirement: process_goal reports awaiting input
`AgentLoop.process_goal()` SHALL return an `AgentResult` with `awaiting_input=True`, `success=False` and an `error` naming the pending task when the Agent Main Loop is waiting on a human task, instead of reporting a timeout.

#### Scenario: Dilemma escalation via process_goal
- **WHEN** `process_goal()` runs a goal whose plan review escalates to the dilemma form
- **THEN** it returns promptly with `awaiting_input=True` and `error` containing "Awaiting human input"

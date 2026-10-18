## ADDED Requirements

### Requirement: The journal records everything a replay needs
The engine SHALL record the route a task chose (`next_route`) on its `task_completed` and
`task_failed` journal events, in every store. Process-property values up to 256,000 characters
SHALL be journalled whole.

#### Scenario: Route recorded
- **WHEN** a task completes with `next_route: "approved"`
- **THEN** its `task_completed` event has `next_route` `approved` after a store round trip

#### Scenario: Large output kept whole
- **WHEN** a task writes a 100,000-character output
- **THEN** the journal holds the full value, not a truncated preview

### Requirement: A finished process can be replayed from its recording
`WorkflowEngine.create_replay` SHALL create a new root process from a COMPLETE or FAILED process
with the same definition and starting properties (without `run_id`). When started, each step SHALL
be served from the original's recorded results instead of running its action: property changes,
output, route, success and error. Manual steps and steps that spawned subflows SHALL be served
the same way. LLM cost properties SHALL NOT be copied.

#### Scenario: Unchanged replay reproduces a failure
- **WHEN** a process that failed at its third step is replayed with no live steps
- **THEN** the replay fails at the same step with the same error and the same workflow properties, and no action runs

#### Scenario: Zero spend
- **WHEN** a process whose LLM steps cost money is replayed
- **THEN** the replay has no `__total_cost__`

#### Scenario: Routes and human steps
- **WHEN** the original took a named route and completed a human task
- **THEN** the replay takes the same route and completes the human step without waiting for input

#### Scenario: Process still running
- **WHEN** a replay of a RUNNING process is requested
- **THEN** `ReplayError` is raised and nothing is created

### Requirement: Selected steps run live
Steps named in `live` SHALL run their actions for real while the rest replays. With a replacement
definition, steps whose definition differs from the original's SHALL run live automatically.
Unknown step ids SHALL raise `ReplayError`.

#### Scenario: Override one step
- **WHEN** a replay names the failing step live and its action now succeeds
- **THEN** only that action runs, its new output is stored, and the remaining steps replay

#### Scenario: Changed definition
- **WHEN** a replacement definition changes one step's prompt
- **THEN** that step runs live and the others are served

### Requirement: A diverging replay fails clearly
When the replay reaches a step occurrence with no recording, or a recording holding a truncated
value, that step SHALL fail with an error naming the step, the occurrence and the reason, and
suggesting running it live.

#### Scenario: Path the original never took
- **WHEN** a live step routes to a step the original never ran
- **THEN** that step fails with "Replay cannot serve step" naming it

#### Scenario: Continue live past the recording
- **WHEN** the replay was created with `continue_live` and a fixed live step leads to steps the original never ran
- **THEN** those steps run live and the replay can complete

### Requirement: Replays can be started from the CLI and the step trace
`manage.py replay_process <process_id> [--live step]... [--definition file]` SHALL start a
replay and print its status as JSON. The step trace SHALL offer a Replay form on each finished
process with steps to run live, redirecting to the replay's trace, which names the process it
replays.

#### Scenario: CLI replay
- **WHEN** `replay_process` runs on a failed process
- **THEN** it prints `{status: failed, replay_of: <id>, ...}` with the original's error

#### Scenario: UI replay
- **WHEN** the user submits the Replay form on a failed process
- **THEN** a replay starts and the browser lands on its trace, marked "Replay of" the original

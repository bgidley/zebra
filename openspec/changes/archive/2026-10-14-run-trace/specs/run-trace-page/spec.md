## ADDED Requirements

### Requirement: Trace page shows every step across parent and subflows
The web UI SHALL provide `/processes/<process_id>/trace/`, which shows the whole run containing that process, from its top-level ancestor down. Each process SHALL list its steps in start order with state, start time, duration, attempts and error, and each subflow SHALL appear nested under the step that spawned it. `/runs/<run_id>/trace/` SHALL redirect to the trace of the run's top-level process.

#### Scenario: Subflow nested under its step
- **WHEN** the "Execute Workflow" step of a run suspends on a "Research Flow" subflow
- **THEN** the trace shows "Research Flow" and its steps inside the "Execute Workflow" step

#### Scenario: Unknown process
- **WHEN** the process or run does not exist
- **THEN** the page returns 404

### Requirement: Steps show historic properties
Each journalled step SHALL show the properties it changed and removed, and SHALL offer the full process properties as they stood after that step, loaded on demand. Each journalled process SHALL offer its starting properties. Engine (`__`-prefixed) properties SHALL be grouped separately.

#### Scenario: Properties after a step
- **WHEN** the user expands "All properties after this step" for the step that set `note`
- **THEN** the snapshot shows `note` with the value it had then, and the engine properties under their own heading

### Requirement: Trace shows where the run is now
While the run is active the page SHALL show the path (process and step names from the top-level process down) to each step that is running, waiting on a human, or waiting on subflows, SHALL mark those steps, and SHALL refresh itself every 5 seconds, keeping expanded sections open. A finished run SHALL show no current step and stop refreshing. Steps still running when their process ended SHALL show as interrupted.

#### Scenario: Run parked on a human task in a subflow
- **WHEN** a subflow is waiting on "Ask the user"
- **THEN** "Where it is now" shows "Agent Main Loop › Execute Workflow › Research Flow › Ask the user"

### Requirement: Runs from before the journal still render
For a process with no journal events the trace SHALL still show the process tree and its live tasks, with a note that no step history was recorded.

#### Scenario: Legacy run
- **WHEN** a process has no journal events
- **THEN** the trace shows the process, its subflows and live tasks, and says it has no step history

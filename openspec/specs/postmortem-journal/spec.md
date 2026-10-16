# postmortem-journal Specification

## Purpose
TBD - created by archiving change postmortem-journal. Update Purpose after archive.

## Requirements

### Requirement: A failed goal run writes a postmortem
When the Agent Main Loop's goal workflow fails, the loop SHALL write a postmortem after recording
the run: what happened, the root cause and the lesson, stored as a `PostmortemEntry` with the run
id, goal, workflow and trigger `failure`. Writing a postmortem SHALL NOT fail the goal.

#### Scenario: Goal workflow fails
- **WHEN** `execute_workflow` completes with `success: false` and the failure is recorded
- **THEN** a postmortem with trigger `failure` is stored for the run and the process still ends FAILED with the goal workflow's error

#### Scenario: Successful run
- **WHEN** the goal workflow succeeds
- **THEN** no postmortem is written

#### Scenario: No LLM available
- **WHEN** the postmortem LLM call fails
- **THEN** nothing is stored and the loop continues

### Requirement: Timed-out and crashed goals get a postmortem
When an Agent Main Loop process ends FAILED without having run its `write_postmortem` step, the
daemon (and `AgentLoop` for direct runs) SHALL start the *Postmortem* system workflow with
trigger `timeout`. Goals cancelled by the kill switch SHALL NOT get one.

#### Scenario: Goal timeout
- **WHEN** a daemon goal is failed by the goal timeout
- **THEN** a *Postmortem* process runs and stores a postmortem with trigger `timeout` and the timeout error

#### Scenario: Kill switch
- **WHEN** a goal is cancelled by the kill switch
- **THEN** no postmortem is started

### Requirement: A low rating writes a postmortem
Rating a run 1 or 2 SHALL start the *Postmortem* workflow in the background with trigger
`low_rating`, the rating and the user's feedback. Only one postmortem SHALL exist per run.

#### Scenario: User rates a run 1
- **WHEN** a successful run is rated 1
- **THEN** a postmortem with trigger `low_rating` is stored for the run

#### Scenario: Already has a postmortem
- **WHEN** a run that already has a postmortem is rated 2
- **THEN** no second postmortem is stored

### Requirement: Lessons are recalled on similar goals
`consult_memory` SHALL retrieve the postmortems most relevant to the goal and include their
lessons in the memory context given to the workflow selector, and the executed goal workflow
SHALL receive them appended to its goal.

#### Scenario: Similar goal after an incident
- **WHEN** a goal similar to one with a stored postmortem is processed
- **THEN** the selector's memory context and the executed child goal both contain that lesson

#### Scenario: No lessons
- **WHEN** no postmortems exist
- **THEN** the memory context and child goal are unchanged

### Requirement: The journal can be browsed
The web UI SHALL show a journal page listing postmortems newest first, each with Zebra's voice
line, the lesson, root cause, what happened, trigger and a link to the run.

#### Scenario: Open the journal
- **WHEN** the user opens `/journal/`
- **THEN** their postmortems are listed newest first with lesson and run link

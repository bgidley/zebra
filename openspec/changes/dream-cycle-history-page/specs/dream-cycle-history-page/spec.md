## ADDED Requirements

### Requirement: Dream cycle history page
The web UI SHALL provide a `/dreams/` page that lists the most recent Dream Cycle processes (at most 20), newest first. It SHALL include only top-level processes of the "Dream Cycle" workflow (any version), whichever user, if any, owns them.

#### Scenario: Only dream cycles are listed
- **WHEN** the store holds Dream Cycle processes and other workflows' processes
- **THEN** the page lists only the Dream Cycle processes, newest first

#### Scenario: No cycles yet
- **WHEN** no Dream Cycle process exists
- **THEN** the page shows an empty state saying no dream cycles have run yet

### Requirement: Each cycle shows what it found and changed
For each cycle the page SHALL show its start time, status and duration. When the step reports are present it SHALL also show the evaluator health score, runs analyzed, changes applied, rejected changes with reasons, curator retirements with rule and reason, continuation counts and the LLM summary.

#### Scenario: Completed cycle
- **WHEN** a completed cycle has a health score of 72, one applied change, one rejected change and one retirement
- **THEN** its card shows "Health 72/100", the changed workflow, the rejection reason and the retired workflow

#### Scenario: Failed cycle
- **WHEN** a cycle failed with `__error__` set
- **THEN** its card shows the error and the failing task

### Requirement: Next scheduled run
The page SHALL show the `dream_cycle` routine's next scheduled run when the routine has run state.

#### Scenario: Routine scheduled
- **WHEN** the `dream_cycle` routine has a stored next run
- **THEN** the page header shows that time in UTC

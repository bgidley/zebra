## ADDED Requirements

### Requirement: Attach a previous run to a new goal

The goal form SHALL let a user optionally select one of their own completed runs to extend, when executing and when queuing. The form SHALL list the user's 10 most recent completed runs. An `?extend_from=<run_id>` link SHALL preselect that run even when it is older than the listed ones. The system SHALL store a `previous_run_context` process property containing the run ID, goal, workflow name, outcome, and output truncated to 2,000 characters.

#### Scenario: Extend link on an older run

- **WHEN** the user opens `/run/?extend_from=<id>` for a completed run of theirs that is not among their 10 most recent
- **THEN** the form lists that run and preselects it

#### Scenario: Another user's run cannot be attached

- **WHEN** a request names a run owned by a different user, or a run that is still in progress
- **THEN** no `previous_run_context` is stored, and `/runs/<id>/context/` returns 404

### Requirement: Previous run context reaches every reasoning step

When `previous_run_context` is present, the ethics gate, workflow selector, workflow creator, workflow variant creator, and the executed goal workflow SHALL receive the goal annotated with the previous run's goal, workflow, outcome, and output. The `goal` process property and the recorded run goal SHALL remain the user's plain goal.

#### Scenario: Reused workflow sees the previous output

- **WHEN** a follow-up goal is routed to an existing workflow
- **THEN** the `goal` property of that workflow's sub-process includes the previous run's output

#### Scenario: Plain goal unchanged without a previous run

- **WHEN** no previous run is attached
- **THEN** every step receives the goal exactly as submitted

### Requirement: Run records its lineage

A run created from a follow-up goal SHALL record `extends_run_id` = the extended run's ID, and the run detail page SHALL link to that run.

#### Scenario: Follow-up run links back

- **WHEN** a follow-up run completes and is recorded
- **THEN** its `extends_run_id` equals the previous run's ID and its detail page shows a "Follow-up to" link

### Requirement: Run lookups are scoped to the requesting user

`DjangoMetricsStore.get_run` SHALL return only runs owned by the current request's user. When no user is set (daemon or system context), it SHALL be unfiltered.

#### Scenario: Cross-user lookup

- **WHEN** user A requests a run owned by user B
- **THEN** `get_run` returns `None`

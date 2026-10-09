## ADDED Requirements

### Requirement: Goals record their submitter
Every goal entry point SHALL start or queue the Agent Main Loop process with `__user_id__` set to
the submitting user's id when that user is known. The entry points are the REST API, the web UI,
continuations, the `queue_goal` task action and the CLI. When the identity is known, the process
SHALL also carry `__user_display_name__` and `__user_identity_id__`.

#### Scenario: Authenticated API goal
- **WHEN** an authenticated user submits `POST /api/goals/`
- **THEN** the Agent Main Loop process has `__user_id__` equal to that user's id
- **AND** it carries the installation's display name and identity id

#### Scenario: Async web view reads identity
- **WHEN** a goal is run or queued from an async web view
- **THEN** the identity is read with the async helper and is not blank when an identity is set

#### Scenario: Goal queued by a workflow
- **WHEN** the `queue_goal` action runs in a process that has `__user_id__`
- **THEN** the queued goal process has the same `__user_id__`, display name and identity id

#### Scenario: CLI goal as a named user
- **WHEN** `zebra goal "<text>" --user alice` is run and the user `alice` exists
- **THEN** the goal process has `__user_id__` equal to alice's id
- **AND** an unknown username exits with an error and runs nothing

#### Scenario: No user
- **WHEN** a goal is run without a user (e.g. CLI without `--user`)
- **THEN** `__user_id__` is `None` and no identity keys are added

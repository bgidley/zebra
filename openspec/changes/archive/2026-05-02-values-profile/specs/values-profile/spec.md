## ADDED Requirements

### Requirement: Per-user values profile

The system SHALL maintain at most one `ValuesProfile` per authenticated user. New users SHALL have no profile until they complete the wizard for the first time. The profile SHALL be scoped by `user_id` consistently with the existing per-user storage pattern.

#### Scenario: New user has no profile

- **WHEN** an authenticated user with no prior profile loads `/profile/values/`
- **THEN** the system starts the wizard in capture mode (no pre-populated values)

#### Scenario: Profile is isolated per user

- **WHEN** user A and user B both have a values profile
- **THEN** queries for user A's profile MUST NOT return any version, tag confirmation, or text from user B's profile

### Requirement: Four free-form text fields

A values profile SHALL contain four text fields: `core_values_text`, `ethical_positions_text`, `priorities_text`, `deal_breakers_text`. Each field SHALL accept free-form prose (no length cap below DB practical limits) and SHALL be stored as part of an immutable `ValuesProfileVersion`.

#### Scenario: User saves all four fields

- **WHEN** the user completes the wizard with text for all four fields
- **THEN** the saved version contains all four field texts exactly as entered

#### Scenario: Empty field is permitted

- **WHEN** the user saves the wizard with one or more fields left empty
- **THEN** the version is saved with empty strings for those fields and the wizard does not block the save

### Requirement: Immutable versioning with monotonic version numbers

Every successful save SHALL create a new `ValuesProfileVersion` row with `version_number = previous_max + 1` for that profile. Existing version rows SHALL never be mutated or deleted. `ValuesProfile.current_version` SHALL point to the most recent version.

#### Scenario: First save creates version 1

- **WHEN** a user with no existing profile completes the wizard
- **THEN** a `ValuesProfile` is created and a `ValuesProfileVersion` with `version_number = 1` is linked as `current_version`

#### Scenario: Subsequent save creates a new version

- **WHEN** a user with `current_version.version_number = N` completes the wizard in edit mode
- **THEN** a new version with `version_number = N + 1` is created, the old version remains in the database unchanged, and `current_version` is updated to point to the new version

### Requirement: Wizard workflow used for both capture and edit

A single Zebra workflow `values_profile_wizard.yaml` SHALL implement both first capture and edit. Edit mode SHALL be signalled by passing `existing_profile_version_id` in the initial process properties. The same workflow steps SHALL run in both modes; only the pre-populated defaults differ.

#### Scenario: Capture mode runs all steps with empty defaults

- **WHEN** the wizard is started without `existing_profile_version_id`
- **THEN** all human-task steps render with empty `default` values and the LLM extraction step receives empty/short text inputs

#### Scenario: Edit mode pre-populates from current version

- **WHEN** the wizard is started with `existing_profile_version_id` pointing to a saved version
- **THEN** each human-task step renders with the corresponding text from that version as the form `default`, and the user can edit any field before saving

### Requirement: `/profile/values/` web entrypoint starts the wizard

The system SHALL expose `/profile/values/` (authenticated). On `GET`, it SHALL determine whether the user has an existing profile, start a process running `values_profile_wizard.yaml` with the appropriate mode, and redirect to the standard pending-task UI.

#### Scenario: Authenticated user with no profile lands on the wizard

- **WHEN** a user with no profile loads `/profile/values/`
- **THEN** the response is a redirect to the first pending task of a freshly created wizard process in capture mode

#### Scenario: Authenticated user with a profile resumes in edit mode

- **WHEN** a user with an existing profile loads `/profile/values/`
- **THEN** the response is a redirect to the first pending task of a freshly created wizard process in edit mode, with `existing_profile_version_id` set to their `current_version`

#### Scenario: Unauthenticated request is rejected

- **WHEN** an unauthenticated user requests `/profile/values/`
- **THEN** the response follows the project's standard auth-required behaviour (redirect to login or 403)

### Requirement: ProfileStore abstracts profile persistence

The system SHALL define a `ProfileStore` abstract base class in `zebra-agent/zebra_agent/storage/interfaces.py` with at minimum: `get_current(user_id)`, `get_version(version_id)`, and `save_version(user_id, version_data)`. The system SHALL provide `InMemoryProfileStore` (CLI/tests) and `DjangoProfileStore` (web) implementations. Task actions SHALL access profile data only through this interface, never via direct ORM queries.

#### Scenario: `save_values_profile` writes via the store

- **WHEN** the `save_values_profile` task action runs at the end of the wizard
- **THEN** it calls `ProfileStore.save_version(user_id, ...)` and never imports a database driver or calls Django ORM directly

#### Scenario: Missing store degrades gracefully

- **WHEN** a task action accesses `context.extras["__profile_store__"]` and finds it `None`
- **THEN** the action logs a warning and returns a sensible default (e.g. `TaskResult.fail(...)` with a clear message), rather than crashing the workflow

### Requirement: System-workflow exclusion

The wizard workflow SHALL be excluded from LLM workflow selection. `zebra_agent/loop.py::_is_system_workflow` SHALL return `True` for the workflow name `"Values Profile Wizard"`.

#### Scenario: Wizard is not selectable for arbitrary goals

- **WHEN** the agent's workflow selector evaluates the available workflow list against a user goal
- **THEN** `"Values Profile Wizard"` is filtered out and is never returned as a candidate

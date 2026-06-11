## ADDED Requirements

### Requirement: Per-domain trust levels with SUPERVISED default
The system SHALL store a trust level — one of `SUPERVISED`, `SEMI_AUTONOMOUS`,
`AUTONOMOUS` — per (user, domain) pair via a `TrustStore` interface with in-memory and
Django/Oracle-backed implementations. A (user, domain) pair that has never been set SHALL
read as `SUPERVISED` without creating a stored record.

#### Scenario: Unset domain reads as SUPERVISED
- **WHEN** `get_trust_level(user_id, "finance")` is called for a user who has never set a
  trust level for `finance`
- **THEN** `SUPERVISED` is returned and no trust-level row is created

#### Scenario: Set then read back
- **WHEN** `set_trust_level(user_id, "code", SEMI_AUTONOMOUS, reason, changed_by)` is
  called and then `get_trust_level(user_id, "code")` is called
- **THEN** `SEMI_AUTONOMOUS` is returned

#### Scenario: Trust levels are user-scoped
- **WHEN** user A sets `code` to `AUTONOMOUS` and user B has not changed any levels
- **THEN** `get_trust_level(B, "code")` still returns `SUPERVISED`

### Requirement: Domain taxonomy registry
The system SHALL maintain a domain registry seeded with the canonical domains `code`,
`scheduling`, `research`, `finance`, `health`, `home`, `creative`, `social`, extensible at
runtime via a registration function. `set_trust_level` SHALL reject domains not present in
the registry. `get_all_trust_levels(user_id)` SHALL return an entry for every registered
domain, defaulting to `SUPERVISED` where no level has been stored.

#### Scenario: Unknown domain rejected on write
- **WHEN** `set_trust_level(user_id, "time-travel", AUTONOMOUS, ...)` is called
- **THEN** the call raises an error and no trust level or audit record is stored

#### Scenario: All domains listed with defaults
- **WHEN** `get_all_trust_levels(user_id)` is called for a user who has only set `code`
- **THEN** all eight seeded domains are returned, `code` with its stored level and the
  other seven as `SUPERVISED`

#### Scenario: Registered custom domain accepted
- **WHEN** `register_domain("gardening")` is called and then
  `set_trust_level(user_id, "gardening", SEMI_AUTONOMOUS, ...)`
- **THEN** the write succeeds and the domain appears in `get_all_trust_levels`

### Requirement: Append-only trust change audit trail
Every successful `set_trust_level` call SHALL append an immutable audit record capturing
user, domain, previous level, new level, reason, who made the change, and a timestamp. The
store SHALL expose `list_trust_changes(user_id, domain=None)` returning records newest
first; it SHALL expose no API to update or delete audit records.

#### Scenario: Change writes an audit record
- **WHEN** `set_trust_level(user_id, "code", SEMI_AUTONOMOUS, "20 clean runs", "ben")` is
  called on a domain previously at `SUPERVISED`
- **THEN** `list_trust_changes(user_id, "code")` returns a record with old level
  `SUPERVISED`, new level `SEMI_AUTONOMOUS`, reason `"20 clean runs"`, changed_by `"ben"`

#### Scenario: History accumulates in order
- **WHEN** a domain's level is changed three times
- **THEN** `list_trust_changes` returns three records, newest first, whose old/new levels
  chain consistently

### Requirement: Trust store available to workflow execution
The web application SHALL inject its trust store into the workflow engine as
`extras["__trust_store__"]` so task actions can query trust levels via
`context.extras.get("__trust_store__")`.

#### Scenario: Task action reads trust level
- **WHEN** a task action retrieves `__trust_store__` from `ExecutionContext.extras` during
  a workflow run in the web app
- **THEN** it receives a `TrustStore` and can call `get_trust_level`

### Requirement: Dashboard shows trust by domain
The web dashboard SHALL display the current trust level of every registered domain for the
logged-in user, read-only.

#### Scenario: Dashboard lists domains and levels
- **WHEN** a logged-in user whose `code` domain is `SEMI_AUTONOMOUS` opens the dashboard
- **THEN** the page shows all registered domains with `code` marked `SEMI_AUTONOMOUS` and
  the rest `SUPERVISED`

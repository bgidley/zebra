## ADDED Requirements

### Requirement: Emergency override reverts all domains to SUPERVISED
The system SHALL provide a one-action emergency override —
`TrustStore.pause_all(user_id, reason, changed_by)`, an authenticated
`POST /api/trust/pause-all/`, and a button on the `/trust/` page — that sets every
registered domain for the user back to SUPERVISED. Each domain that was not already
SUPERVISED SHALL get a trust change audit record (reason prefixed "Emergency override:",
the triggering user as `changed_by`). Because trust gates read the level at execution
time, running autonomous workflows SHALL observe the revert at their next gate.

#### Scenario: Override reverts elevated domains and audits them
- **WHEN** a user with `code` at AUTONOMOUS and `scheduling` at SEMI_AUTONOMOUS triggers
  the emergency override
- **THEN** both domains read SUPERVISED afterwards, the change history shows an
  "Emergency override" record for each with the user as `changed_by`, and the action
  reports the two reverted domains

#### Scenario: Override is idempotent on already-supervised domains
- **WHEN** the override runs for a user whose domains are all SUPERVISED
- **THEN** no trust level changes and no new audit records are written

#### Scenario: Previously-autonomous workflow requires approval after override
- **WHEN** a `code`-domain workflow's `trust_gate` proceeds while `code` is AUTONOMOUS,
  the user then triggers the emergency override, and the workflow reaches another
  `trust_gate`
- **THEN** the later gate routes to approval because `code` is now SUPERVISED

#### Scenario: Override requires authentication
- **WHEN** an unauthenticated client calls `POST /api/trust/pause-all/`
- **THEN** the request is rejected and no trust level changes

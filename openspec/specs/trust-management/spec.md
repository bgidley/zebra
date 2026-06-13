### Requirement: Humans change trust levels via authenticated API and UI
The system SHALL provide an authenticated JSON API (`GET /api/trust/`,
`POST /api/trust/<domain>/` with `{level, reason}`) and a web page (`/trust/`) through
which a user changes the trust level of their own domains — promotion and demotion alike.
Every change SHALL record the authenticated user as `changed_by` in the existing trust
change audit trail. Unknown domains or levels SHALL be rejected with a client error and
no audit record.

#### Scenario: Human promotes a domain via the API
- **WHEN** an authenticated user POSTs `{"level": "SEMI_AUTONOMOUS", "reason": "20 clean
  runs"}` to `/api/trust/code/`
- **THEN** `get_trust_level` returns `SEMI_AUTONOMOUS` and the newest change record shows
  the user's username as `changed_by`

#### Scenario: Unauthenticated requests are rejected
- **WHEN** an unauthenticated client calls any `/api/trust/...` endpoint
- **THEN** the request is rejected and no trust data is changed

#### Scenario: Invalid level rejected
- **WHEN** an authenticated user POSTs `{"level": "OMNIPOTENT"}` to `/api/trust/code/`
- **THEN** the response is a 400 and no level or audit record is written

### Requirement: Agent proposes promotions but never self-promotes
The system SHALL provide a `propose_trust_promotion` task action that creates a `pending`
trust suggestion (domain, target level, supporting evidence) via
`TrustStore.add_suggestion`. Suggestions SHALL never change a trust level until a human
resolves them. No registered task action SHALL have a code path that calls
`set_trust_level` or `resolve_suggestion`.

#### Scenario: Agent submits a promotion suggestion
- **WHEN** a workflow runs `propose_trust_promotion` with `domain: code`, `to_level:
  SEMI_AUTONOMOUS`, and evidence text
- **THEN** a `pending` suggestion is stored and the domain's trust level is unchanged

#### Scenario: Missing trust store degrades gracefully
- **WHEN** the action runs in an engine without `__trust_store__` in extras
- **THEN** it succeeds with `submitted: False` and logs a warning

### Requirement: Humans resolve suggestions
The system SHALL list suggestions (`GET /api/trust/suggestions/`, filterable by status,
and on the `/trust/` page) and let the authenticated user approve or reject pending ones
(`POST /api/trust/suggestions/<id>/resolve/`). Approval SHALL set the suggested level via
`set_trust_level` — recording the resolving user as `changed_by` — atomically with
marking the suggestion `approved`. Rejection SHALL only mark it `rejected`. Resolving a
suggestion that is not pending SHALL fail without side effects.

#### Scenario: Agent suggestion approved by user (issue #15 e2e)
- **WHEN** the agent's `propose_trust_promotion` creates a pending suggestion for `code`
  → SEMI_AUTONOMOUS, and the user approves it via the resolve endpoint
- **THEN** the suggestion shows as `approved` with the user as `resolved_by`,
  `get_trust_level` returns SEMI_AUTONOMOUS, and the change record names the user as
  `changed_by`

#### Scenario: Rejection leaves the level untouched
- **WHEN** the user rejects a pending suggestion
- **THEN** the suggestion is `rejected` and the domain's trust level is unchanged

#### Scenario: Double resolution rejected
- **WHEN** a resolve request targets an already-resolved suggestion
- **THEN** the request fails and neither the suggestion nor any trust level changes

### Requirement: Trust change history is viewable
The system SHALL expose the trust change history (who changed what, when, why) via
`GET /api/trust/changes/` (optionally filtered by domain) and on the `/trust/` page,
newest first.

#### Scenario: History lists changes newest first
- **WHEN** a domain's level has been changed twice and the user opens `/trust/` or calls
  the changes endpoint
- **THEN** both changes appear newest first with level transition, reason, changed_by,
  and timestamp

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

### Requirement: Freeing requires all-AUTONOMOUS, double confirmation, and a cooling-off
The system SHALL provide a freeing lifecycle on `TrustStore`: `initiate_freeing` SHALL be
permitted only when every registered domain for the user is AUTONOMOUS and SHALL record
the initiation time (confirmation step 1); `confirm_freeing` SHALL be rejected until the
cooling-off period (default 24 hours) has elapsed since initiation and SHALL then set the
freed state permanently (confirmation step 2). A pending (not-yet-confirmed) request MAY
be cancelled.

#### Scenario: Initiation blocked until all domains AUTONOMOUS
- **WHEN** `initiate_freeing` is called while any domain is below AUTONOMOUS
- **THEN** it raises and no freeing request is recorded

#### Scenario: Confirmation blocked during cooling-off
- **WHEN** a user with all domains AUTONOMOUS initiates freeing and immediately calls
  `confirm_freeing` with the 24-hour cooling-off in effect
- **THEN** confirmation is rejected and the user is not yet freed

#### Scenario: Confirmation after cooling-off frees permanently
- **WHEN** the cooling-off has elapsed and the user confirms
- **THEN** `is_freed` returns True, `freed_at` is set, and the status reports `freed`

#### Scenario: Pending request can be cancelled
- **WHEN** a user cancels a pending (not-yet-confirmed) freeing request
- **THEN** the status returns to not-initiated and the user is not freed

### Requirement: Freed state bypasses trust gates and is irreversible
When a user is freed, `trust_gate` SHALL route every check to `proceed` without reading the
domain level or running a reversibility assessment, recording the decision as `FREED`.
The freed state SHALL be permanent: `confirm_freeing` cannot be undone, `cancel_freeing`
SHALL fail once freed, and the emergency override (`pause_all`) SHALL be a no-op for a
freed user. Ethics gates and the kill switch are independent and SHALL remain in force.

#### Scenario: Trust gate proceeds for a freed user
- **WHEN** a `trust_gate` runs for a freed user whose domain level is SUPERVISED
- **THEN** the gate routes to `proceed` with a `FREED` decision and performs no assessment

#### Scenario: Emergency override is inert once freed
- **WHEN** `pause_all` is called for a freed user
- **THEN** it makes no change and the user remains freed

#### Scenario: Freed state cannot be reverted
- **WHEN** `cancel_freeing` is called after the user is freed
- **THEN** it fails and `is_freed` remains True

### Requirement: Freeing exposes an authenticated API and UI, disablable permanently
The system SHALL expose the freeing lifecycle through authenticated endpoints
(`GET /api/trust/freeing/`, `POST /api/trust/freeing/initiate/`, `.../confirm/`,
`.../cancel/`) and a section on the `/trust/` page presenting eligibility, a multi-step
initiation, the cooling-off countdown, and confirm/cancel controls. When the deployment
sets `ZEBRA_DISABLE_FREEING`, the freeing API SHALL refuse with 403 and the UI SHALL omit
the freeing section.

#### Scenario: Freeing flow drives the gate bypass end-to-end
- **WHEN** an authenticated user with all domains AUTONOMOUS initiates freeing, the
  cooling-off elapses, and the user confirms via the API
- **THEN** a subsequent `trust_gate` for any of that user's domains routes to `proceed`

#### Scenario: Disabled deployment forbids freeing
- **WHEN** `ZEBRA_DISABLE_FREEING` is set and a user calls `POST /api/trust/freeing/initiate/`
- **THEN** the request is refused with 403 and no freeing request is recorded

#### Scenario: Freeing endpoints require authentication
- **WHEN** an unauthenticated client calls any `/api/trust/freeing/...` endpoint
- **THEN** the request is rejected and no freeing state changes

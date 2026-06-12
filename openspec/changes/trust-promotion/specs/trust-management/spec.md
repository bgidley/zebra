## ADDED Requirements

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

## ADDED Requirements

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

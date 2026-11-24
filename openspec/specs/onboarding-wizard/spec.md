# onboarding-wizard Specification

## Purpose
TBD - created by archiving change onboarding-wizard-shell. Update Purpose after archive.

## Requirements

### Requirement: Switch
The wizard SHALL be available only while `ZEBRA_ONBOARDING_ENABLED` is on AND the owner's
`SystemStateModel.onboarding_enabled` toggle is on. While off, every wizard URL SHALL return 404
and SHALL create nothing. Only the owner SHALL change the toggle.

#### Scenario: Off
- **WHEN** either switch is off and a visitor requests any `/onboarding/` wizard URL
- **THEN** the response is 404 and no process or user is created

#### Scenario: Non-owner toggle
- **WHEN** a signed-in user who is not the owner posts to `/onboarding/manage/`
- **THEN** the response is 403 and the toggle is unchanged

### Requirement: Anonymous resumable session
A session SHALL be one *Onboarding* process with no user. The visitor SHALL hold a signed token
`{process_id, nonce}` in an HttpOnly cookie and a resume link; the process SHALL store only the
SHA-256 of the nonce. Resuming SHALL load that one process by id and compare the hash. A new link
SHALL rotate the nonce; "forget me" SHALL rotate it and fail the process.

#### Scenario: Resume in a new browser
- **WHEN** a visitor at step 2 opens their resume link in a browser with no cookie
- **THEN** the wizard shows step 2

#### Scenario: Old link after rotation
- **WHEN** the visitor makes a new link and the old link is opened
- **THEN** the response is 410 and the session is not shown

### Requirement: Steps, failure and retry
The wizard SHALL show each step's what happens, cost and undo. Only the session's current READY
visitor task SHALL be completable, and only by one of its routes. A step reported as failed SHALL
show its reason and a retry; later steps SHALL stay locked.

#### Scenario: Failure
- **WHEN** the visitor reports a problem on step 1
- **THEN** the wizard shows the reason and "Try this step again", and steps 2-6 are locked

#### Scenario: Skipping ahead
- **WHEN** a request names a task id that is not the current step
- **THEN** the response is 409 and nothing is completed

### Requirement: No secrets, no users, no list queries
Wizard forms SHALL refuse private keys and API keys. No wizard code path SHALL create a user or
reach a passkey view, and wizard views SHALL NOT call store list queries.

#### Scenario: Private key pasted
- **WHEN** a field holds `-----BEGIN ... PRIVATE KEY-----`
- **THEN** the form is shown again with an error and nothing is stored

### Requirement: Launch of the built-in only
A session SHALL start through `create_library_process(entry="onboarding")` for an allowlisted
workflow whose library content hash is a shipped built-in's, and SHALL be started at once.

#### Scenario: Shadowed workflow
- **WHEN** the library's *Onboarding* differs from the shipped file
- **THEN** starting is refused with 503 and no process is created

### Requirement: Share the onboarding link
The system SHALL give signed-in users a main-navigation entry and page `/invite/` showing the public onboarding URL built from the configured public https origin (`PUBLIC_BASE_URL`, else an https `CSRF_TRUSTED_ORIGINS` entry), never from the request Host header, with no user identity in it. The entry and page SHALL be absent (404) while onboarding is off.

#### Scenario: Hostile Host header
- **WHEN** the page is requested with a different Host header
- **THEN** the link still uses the configured origin

#### Scenario: Off
- **WHEN** onboarding is off
- **THEN** `/invite/` returns 404 and the nav entry is not rendered

#### Scenario: No origin configured
- **WHEN** no https origin is configured
- **THEN** the page shows no link and says how to set `ZEBRA_PUBLIC_BASE_URL`

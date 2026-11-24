# onboarding-signup Specification

## Purpose
TBD - created by archiving change onboarding-signup. Update Purpose after archive.

## Requirements

### Requirement: Signup guide
The system SHALL serve the versioned signup guide as the wizard's signup step at `/onboarding/`, to an anonymous visitor holding a resume token, with no login. It SHALL state before the signup steps that the home region (`uk-london-1`) cannot be changed, and before the form that Pay-As-You-Go can take 1-2 days and the visitor should not wait. `/onboarding/signup/` and `/onboarding/signup/confirm/` SHALL redirect to `/onboarding/` and return 404 while onboarding is off (env AND owner switch).

#### Scenario: Off
- **WHEN** onboarding is off by the environment or the owner switch
- **THEN** the signup and confirm URLs return 404, for GET and POST

#### Scenario: On
- **WHEN** an anonymous visitor starts a session
- **THEN** step 1 shows the guide version, the region and 1-2 day warnings, and every external link opens with `target="_blank" rel="noopener"`

### Requirement: Pre-flight validation
The system SHALL validate a pasted tenancy OCID and region id by shape only, make no network calls, refuse secret-shaped input without storing or echoing it, and keep the accepted values in the visitor's process properties, not in a table.

#### Scenario: Secret pasted
- **WHEN** a private key is pasted into the OCID field
- **THEN** the response is 400, nothing is stored and the value is not shown

#### Scenario: Resume
- **WHEN** a visitor completes the step and resumes from another browser with the link
- **THEN** the wizard is at step 2, shows the region and Pay-As-You-Go status, and another visitor sees none of it

### Requirement: Next-step lock
The system SHALL refuse to complete the signup step until "account created" and "budget alert understood" are ticked, and SHALL record Pay-As-You-Go as `pending` when it was requested and not yet reported active.

#### Scenario: Not ticked
- **WHEN** the step is submitted without the budget tick
- **THEN** it is refused and step 2 stays locked

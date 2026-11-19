# onboarding-signup Specification

## Purpose
TBD - created by archiving change onboarding-signup. Update Purpose after archive.

## Requirements

### Requirement: Signup guide
The system SHALL serve a versioned signup guide at `/onboarding/signup/` for signed-in users, returning 404 while `ONBOARDING_ENABLED` is off. It SHALL state before the signup steps that the home region (`uk-london-1`) cannot be changed, and before the form that Pay-As-You-Go can take 1-2 days and the user should not wait.

#### Scenario: Off
- **WHEN** `ONBOARDING_ENABLED` is off
- **THEN** the guide and confirm URLs return 404

#### Scenario: On
- **WHEN** a signed-in user opens the guide
- **THEN** the page shows its version, the region warning and the 1-2 day warning, and every external link opens with `target="_blank" rel="noopener"`

### Requirement: Pre-flight validation
The system SHALL validate a pasted tenancy OCID and region id by shape only, make no network calls, refuse secret-shaped input without storing or echoing it, and store the accepted values per user.

#### Scenario: Secret pasted
- **WHEN** a private key is pasted into the OCID field
- **THEN** the response is 422, nothing is stored and the value is not shown

#### Scenario: Resume
- **WHEN** a user saves valid answers and reopens the page
- **THEN** the saved OCID, region, ticks and Pay-As-You-Go status are shown, and another user sees none of them

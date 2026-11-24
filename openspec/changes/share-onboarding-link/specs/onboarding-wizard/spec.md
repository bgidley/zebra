## ADDED Requirements

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

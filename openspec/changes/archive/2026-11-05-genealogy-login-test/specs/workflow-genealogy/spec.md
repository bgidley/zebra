## ADDED Requirements

### Requirement: Genealogy and Commons pages require login
With the production middleware stack, an anonymous GET of `/workflows/<name>/genealogy/` or
`/commons/` SHALL redirect to `LOGIN_URL` (with `next`), and an authenticated GET SHALL render the
page. A unit test SHALL check this against the `MIDDLEWARE` declared in `settings.py`, so removing
`LoginRequiredMiddleware` or exempting either view fails CI.

#### Scenario: Anonymous visitor is redirected
- **WHEN** an anonymous visitor requests `/workflows/Old%20Search/genealogy/` or `/commons/`
- **THEN** the response is a 302 to `/auth/login/?next=<path>`

#### Scenario: Logged-in owner sees the page
- **WHEN** a logged-in user requests the same pages
- **THEN** each response is 200

#### Scenario: Guard removed
- **WHEN** the genealogy view is marked `login_not_required` or `LoginRequiredMiddleware` is removed from `settings.MIDDLEWARE`
- **THEN** the test fails

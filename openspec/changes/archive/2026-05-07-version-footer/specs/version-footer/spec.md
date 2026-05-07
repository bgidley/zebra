## ADDED Requirements

### Requirement: Version endpoint returns git metadata
The system SHALL expose a `GET /api/version/` endpoint that returns a JSON object containing
the current git commit short hash, commit date, and a list of recent commits from the master branch.
The endpoint SHALL be accessible without authentication.
The response SHALL include at least the most recent 10 commits.
When git is unavailable or the repository has no history, the endpoint SHALL return a degraded
response with `"short_hash": "unknown"` and an empty `commits` list rather than raising an error.

#### Scenario: Successful version fetch
- **WHEN** a client sends `GET /api/version/`
- **THEN** the response is HTTP 200 with `Content-Type: application/json`
- **THEN** the body contains `short_hash` (7-char hex string), `date` (ISO date), and `commits` (array)
- **THEN** each commit entry has `hash`, `date`, and `subject` fields


### Requirement: Version footer is shown on every page
The system SHALL render a persistent footer strip at the bottom of every page that extends
`base.html`. The footer SHALL display the short git commit hash and date in a compact,
unobtrusive style (small text, muted colour).

#### Scenario: Footer visible on dashboard
- **WHEN** an authenticated user visits any page that extends `base.html`
- **THEN** a footer element is present in the DOM containing the short commit hash

#### Scenario: Footer shown without authentication on setup page
- **WHEN** the setup page is rendered (before any user exists)
- **THEN** the footer is still visible

### Requirement: Clicking the footer reveals a recent-changes panel
The system SHALL allow users to click (or tap) the version footer to toggle an overlay panel
that lists the most recent commits. The panel SHALL show each commit's short hash, date, and
subject line. The panel SHALL be dismissible by clicking the footer again or clicking outside it.

#### Scenario: User expands the panel
- **WHEN** the user clicks the version footer strip
- **THEN** a panel appears showing a list of recent commits (hash, date, subject)
- **THEN** each commit row is rendered in a readable monospace or code-style font

#### Scenario: User collapses the panel
- **WHEN** the panel is open and the user clicks the footer strip again
- **THEN** the panel closes

#### Scenario: Commit data is fetched once
- **WHEN** the page loads
- **THEN** the browser fetches `/api/version/` exactly once
- **THEN** subsequent open/close toggles do not trigger additional network requests

### Requirement: Version metadata is baked at image build time
The CI/CD deploy stage SHALL generate a `version.json` file from `git log` before building the
Docker image. The Dockerfile SHALL copy `version.json` into the image. The Django app SHALL read
`version.json` once in `AppConfig.ready()` and cache it for the lifetime of the process. It
SHALL NOT invoke `git` at runtime. If `version.json` is absent (local dev, test), the app SHALL
fall back to `{"short_hash": "unknown", "date": "", "commits": []}`.

#### Scenario: Metadata available immediately after container start
- **WHEN** the Docker image was built by CI with `version.json` present
- **THEN** `GET /api/version/` responds with the correct `short_hash` and non-empty `commits`

#### Scenario: Graceful fallback when version.json is absent
- **WHEN** the app starts without a `version.json` file (e.g. local dev)
- **THEN** `GET /api/version/` returns HTTP 200 with `short_hash` equal to `"unknown"` and `commits` equal to `[]`

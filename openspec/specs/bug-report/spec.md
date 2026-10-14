# bug-report Specification

## Purpose
TBD - created by archiving change bug-report-button. Update Purpose after archive.

## Requirements

### Requirement: Report a bug from any signed-in page
The web UI SHALL show a "Report a bug" button on every page that uses the main layout. It SHALL open a dialog asking for a title, what happened, what was expected, steps to reproduce and a severity.

#### Scenario: Button opens the dialog
- **WHEN** a signed-in user clicks "Report a bug" in the sidebar
- **THEN** a dialog with title, what happened, expected, steps and severity fields is shown

### Requirement: Capture the technical view
A submitted report SHALL include client context collected by the browser (page URL, title, referrer, user agent, viewport, time zone, recent console errors and failed HTMX requests) and server context (build version, user, server time, resolved route, and the state of any process, task or run named in the page URL).

#### Scenario: Process page is linked
- **WHEN** a report is submitted from a page whose URL names a process or task
- **THEN** the stored technical context includes that process's state, workflow name and error

#### Scenario: Bad client context is not fatal
- **WHEN** the client context is missing, not a JSON object, or over 64 KB
- **THEN** the report is still recorded, with a note in place of the client context

### Requirement: Report is stored as a workflow
Submitting a report SHALL start a "Bug Report" process holding the user's report, the technical context and a markdown summary as process properties. The workflow SHALL be tagged `system` so the goal selector never chooses it.

#### Scenario: Valid report starts a workflow
- **WHEN** a signed-in user submits a report with a title and a description
- **THEN** a running "Bug Report" process exists with those properties and a pending "Review Bug Report" task

#### Scenario: Missing fields are rejected
- **WHEN** a report is submitted without a title or without a description
- **THEN** the response is 400 and no process is created

#### Scenario: Signed-out users cannot report
- **WHEN** an unauthenticated request posts a report
- **THEN** no process is created

### Requirement: Reports can be reviewed
The "Review Bug Report" human task SHALL show the markdown summary and collect a verdict, priority, optional issue link and notes. Completing it SHALL complete the process. A `/bugs/` page SHALL list recent reports, newest first, with title, severity, state and review verdict.

#### Scenario: Review completes the report
- **WHEN** the reviewer submits the review task with a verdict
- **THEN** the process is complete and `/bugs/` shows the verdict

#### Scenario: Open reports are listed
- **WHEN** a user opens `/bugs/`
- **THEN** each recent report is listed with a link to its review task while it is open

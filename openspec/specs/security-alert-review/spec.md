# security-alert-review Specification

## Purpose
TBD - created by archiving change github-security-alerts. Update Purpose after archive.

## Requirements
### Requirement: Post-merge security alert review
After every merge to master the delivery flow SHALL run `scripts/github-security-alerts.sh` with
the merge sha. The script SHALL wait (default 900 s) for a CodeQL analysis of that commit for each
analysed language, then list every open Dependabot, CodeQL and secret-scanning alert of the GitHub
mirror, and exit 0 when none are open, 2 when some are open and 1 when it cannot check.

#### Scenario: Nothing open
- **WHEN** the merge commit has been analysed and no alert is open
- **THEN** the script prints "No open security alerts." and exits 0

#### Scenario: Alerts open
- **WHEN** any Dependabot, CodeQL or secret-scanning alert is open
- **THEN** the script lists each one (number, severity, package or rule, location) and exits 2

#### Scenario: Cannot check
- **WHEN** `gh` is missing, unauthenticated or an alert listing fails
- **THEN** the script exits 1 and says why

#### Scenario: Analysis late
- **WHEN** no CodeQL analysis of the merge sha arrives within the wait
- **THEN** the script prints a warning naming the missing languages and still lists the alerts

### Requirement: Alerts are resolved, never ignored
An open alert introduced by the merged change SHALL be fixed before sign-off. Any other open alert
SHALL be fixed, filed as a follow-up issue with the `security` label, or dismissed on GitHub with a
written reason when it is a false positive.

#### Scenario: New CodeQL finding in touched code
- **WHEN** the review lists a CodeQL alert in a file the merged branch changed
- **THEN** the change is not signed off until a fix is merged

### Requirement: No exception text in web responses
A web or API view SHALL NOT return an unhandled exception's text in a 5xx response; it SHALL log
the exception and return a generic message. Exception text in a 4xx HTML response SHALL be HTML
escaped. A failed WebAuthn verification SHALL answer only "Verification failed".

#### Scenario: Queue failure
- **WHEN** queuing a goal from the web form raises an unexpected exception
- **THEN** the response is a 500 whose body contains none of the exception's text

#### Scenario: Passkey verification failure
- **WHEN** WebAuthn registration verification raises
- **THEN** the response is 400 `{"error": "Verification failed"}`

### Requirement: Linear template stripping
Removing `{{…}}` templates from text before scanning (leak guard, PII scan, confidentiality scan)
SHALL take linear time and give the same result as replacing each lazy `{{.*?}}` match (DOTALL)
with a space.

#### Scenario: Unclosed openers
- **WHEN** a literal is 200,000 repetitions of `{{` with no `}}`
- **THEN** it is returned unchanged in under a second

### Requirement: No personal knowledge values in logs
Knowledge-resolution logging SHALL name entries by id or key, never by their value.

#### Scenario: Use the new value
- **WHEN** a contradiction is resolved with `use_new`
- **THEN** the log line names the entry id and not the value

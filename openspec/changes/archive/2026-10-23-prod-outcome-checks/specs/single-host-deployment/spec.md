## ADDED Requirements

### Requirement: Post-deploy smoke covers logged-in pages
The `smoke` job SHALL log in as the `smoke` user with a session minted by
`manage.py smoke_session` (a session key on stdout, expiring after `--minutes`, default 15) and
SHALL check the dashboard, `/tasks/`, `/nav/needs-you/` and the budget API with it. A missing or
inactive `smoke` user SHALL fail the command, and so the job.

#### Scenario: Logged-in checks run
- **WHEN** the `smoke` job runs after a deploy
- **THEN** the dashboard, `/tasks/` (inbox or empty state, not the login page), `/nav/needs-you/` and budget tests run and pass instead of skipping

#### Scenario: Short-lived session
- **WHEN** `manage.py smoke_session --minutes 5` runs
- **THEN** it prints a session key that authenticates as `smoke` and expires in 300 seconds

#### Scenario: No smoke user
- **WHEN** no active `smoke` user exists
- **THEN** `smoke_session` exits non-zero and prints no key

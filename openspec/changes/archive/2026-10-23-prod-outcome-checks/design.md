## Context

Smoke tests run on the host shell runner after deploy, against prod on `localhost:8000`. Prod
login is passkey-only; the deploy keeps a password `smoke` user for the API's HTTP Basic auth,
which web views do not accept. `tests/smoke/conftest.py` already reads `ZEBRA_SMOKE_SESSION` and
skips without it.

## Decisions

- **Mint a DB session in the container**, not a login flow: `manage.py smoke_session` writes a
  session with the auth keys Django's `login()` sets (user pk, first `AUTHENTICATION_BACKENDS`
  entry, session auth hash) and a 15-minute expiry. It prints only the key (logs go to stderr),
  so the CI line is a plain command substitution; under GitLab's `set -eo pipefail` a failure
  fails the job instead of silently skipping the tests again.
- **Timeout vs failure from the error text**: the engine's goal timeout writes
  "Timed out after Ns" and `AgentLoop` "Agent loop timed out"; anything else that ended a goal
  unreflected is a crash. Matching "timed out" case-insensitively covers both without new state.

## Risks

- The `smoke` user is not a superuser; the pages tested need only a login (single-user identity).
- A leaked smoke session lasts at most 15 minutes and grants the `smoke` user's access only.

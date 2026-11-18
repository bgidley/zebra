## Context

Decisions on #277 (2026-11-04/09): London `uk-london-1` default (Newport lacks Always Free 26ai, Oracle docs confirm London does have it), Arm 2 OCPU / 12 GB, PAYG strongly advised with a 1-2 day delay, home region permanent. See `specs/onboarding-signup-design.md`.

## Decisions

- Sync Django views, login required, namespaced `onboarding_*`, no dependency on the #276 shell.
- State in its own table (`zebra_onboarding_signup`, `user_id` unique, JSON `data`) so #276 can later read or migrate it.
- Region shape is a regex; the 26ai allowlist only produces a warning, so a new Oracle region is not blocked.
- Fallback region named in the page is the other 26ai regions Oracle lists; London A1 capacity is flagged as unverifiable.

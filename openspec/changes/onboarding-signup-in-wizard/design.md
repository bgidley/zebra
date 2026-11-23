## Context

See specs/onboarding-signup-design.md (updated) and specs/onboarding-design.md section 2.

## Decisions

- State is the signup task's output in process properties; no table. The tenancy OCID is an account identifier, not a secret, kept only for the session's life (30 days idle, "forget me" fails the process).
- Validation extends `step_output` with a per-step validator (`signup`), reusing `onboarding_preflight`; rejected fields are dropped from the re-rendered form.
- Guide HTML is a partial rendered in the wizard for the signup step; `ONBOARDING_GUIDE_VERSION` moves to `onboarding_preflight`.
- Legacy URLs: one `login_not_required`, `csrf_exempt` view that 404s when off, else redirects (303) to `/onboarding/`.
- Migration 0039 deletes the model (reversible: Django recreates it). 0037/0038 are applied in prod Oracle; the table has 0 rows.

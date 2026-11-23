# Onboarding signup guide and pre-flight (#277, moved into the wizard by #312)

## Goal & scope
Guide a visitor with no Oracle Cloud account through signup and take non-secret pre-flight answers. Guidance and shape checks only; no OCI calls. Part of epic #275. GitLab #277 (built), #312 (account-less move; Option A decided 2026-11-22). Real checks come with #279.

## Data model
None of its own. `OnboardingSignupModel` and its table (migration 0037) are gone: migration 0039 deletes the model (0037 stays in history; it and 0038 were applied in prod Oracle, the table held 0 rows; 0039 is reversible, Django recreates the empty table). The answers are the output of the wizard's `signup` task, i.e. the visitor's Onboarding process property `__task_output_signup` (see [onboarding-design.md](onboarding-design.md) section 2): `{tenancy_ocid, home_region, payg: none|pending|active, account_created, admin_mfa, payg_requested, budget_ack}`. Keyed by the process the resume token names; gone when the session is forgotten or expires. The tenancy OCID is an account identifier, not a secret; it is kept only in that process. No secrets, ever.

## API / interface
- The guide is the signup step (step 1) of `/onboarding/`: partial `templates/onboarding/partials/signup_guide.html` above the step form, anonymous, served with the resume cookie or link. Later steps show an account summary (home region, Pay-As-You-Go status).
- `/onboarding/signup/` and `/onboarding/signup/confirm/` (GET or POST, no login, CSRF-exempt, nothing read or stored) 302 to `/onboarding/`; 404 while onboarding is off (`onboarding.is_enabled()`: env AND owner switch, #321).
- Validators in `api/onboarding_preflight.py`: tenancy `ocid1.tenancy.oc<n>..<id>`, region `area-city-n`, secret shapes refused (`check_signup`, called by `onboarding.step_output` for the signup step). A rejected value is dropped from the stored output and from the re-rendered form, and is not named in the error.
- `scripts/check_onboarding_links.py`: link check of the Oracle URLs in the guide partial.

## Control flow
"Account created" and "budget alert understood" are required ticks: the step cannot complete without them, so step 2 stays locked server-side (partly #318; the self-attested budget tick is replaced by the real alert check in #279). A requested upgrade while status is "none" is stored as `pending` and shown as "upgrade pending" on later steps (partly #317; setting it from a click on the upgrade link, and `active` from the tenancy subscription status, wait for #279). The `problem` route stores only the visitor's text (secret-refused).

## Configuration
`ZEBRA_ONBOARDING_ENABLED` plus the owner switch (see onboarding-design.md). Guide text version `ONBOARDING_GUIDE_VERSION` / `ONBOARDING_GUIDE_CHECKED` in `onboarding_preflight.py`; bump with any text change.

## Content provenance (checked 2026-11-16, Oracle docs)
Confirmed: A1 = 2 OCPU / 12 GB for Always Free tenancies; 200 GB block+boot; two Always Free ADBs at 20 GB; 10 TB/month egress; idle compute reclamation (7 days, p95 CPU/network/memory under 20%); ADB stopped after 7 idle days and possibly deleted after 90 stopped days; 26ai regions include London, not Newport. Marked "needs verification" on the page: the 1-2 day upgrade delay and capacity priority, A1 capacity in London, card hold and trial credit details, sign-up UI steps.

## Open questions
Fallback region if London capacity is poor (the page lists Oracle's other 26ai regions). #317 and #318 stay open for the parts that need #279.

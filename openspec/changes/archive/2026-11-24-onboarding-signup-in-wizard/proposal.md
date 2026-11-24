## Why

The wizard (#276) is account-less, but the merged #277 signup guide sits behind login and keeps per-user state in `OnboardingSignupModel`. Two signup surfaces, one needing an account, contradicts the design. Owner decision on #312: Option A, move the guide into the wizard.

## What Changes

- The wizard's step 1 ("Oracle Cloud account") shows the static, versioned signup guide and takes the pre-flight answers (tenancy OCID, home region, Pay-As-You-Go status, "I've done this" ticks). No login; reached with the resume token.
- Pre-flight answers live in the visitor's Onboarding process properties (`__task_output_signup`), keyed by the process the resume token names. Shape checks (OCID, region) and secret refusal run server-side on submit; a rejected value is neither stored nor echoed.
- "Pay-As-You-Go requested" ticked while the status says "none" is recorded as `pending` (part of #317). The wizard shows the account summary (region, upgrade pending) on later steps.
- The required ticks (account created, budget alert understood) are enforced server-side before step 2 unlocks (part of #318).
- **BREAKING (internal)**: `OnboardingSignupModel` is removed (migration 0039 deletes the empty table; 0037 stays in history, already applied in prod). `/onboarding/signup/` and `/onboarding/signup/confirm/` redirect to `/onboarding/`, 404 while onboarding is off (env AND owner switch).

## Non-goals

- Setting `pending` from a click on the upgrade link, `active` from the tenancy subscription status, and the real budget-alert check (#317, #318 stay open for #279).
- Any change to the session token format (#276 S3/S4 build on it).

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | An anonymous visitor sees the signup guide and pre-flight as step 1 of the wizard, with no login and no user row created | View test: guide content present on `/onboarding/` for a fresh session; user count unchanged |
| O2 | Pre-flight answers persist in the process properties, resume with the token and are not visible to another visitor; no table stores them | Tests: resume from a second browser, second session sees none, `OnboardingSignupModel` gone |
| O3 | Secret-shaped input and malformed OCID/region are refused, never stored or echoed | Tests: 400 with message, absent from properties and HTML |
| O4 | Step 2 stays locked until the account and budget ticks are set; "upgrade requested" shows as pending | Tests: submit without ticks refused, pending summary shown |
| O5 | Old `/onboarding/signup/*` URLs redirect to the wizard and 404 while off (env or owner switch), including POST; migration 0039 applies and reverses | Tests, prod migrate |

## Why

A user with no Oracle Cloud account must reach the wizard with a usable tenancy (#277, epic #275). We cannot sign up for them, so Zebra gives a versioned guide with the decided choices (London home region, Pay-As-You-Go advised but not awaited, Always Free 2 OCPU / 12 GB) and a no-network pre-flight form.

## What Changes

- `/onboarding/signup/`: a static, versioned guide (version + checked date on the page), Oracle links in new tabs, unverifiable claims marked "Needs verification". 404 while `ONBOARDING_ENABLED` is off (default off).
- `/onboarding/signup/confirm/` (POST): pure-shape validation of tenancy OCID and region id, secret-shaped input refused, self-reported Pay-As-You-Go status (`none|pending|active`), "I've done this" ticks, stored per user (`OnboardingSignupModel`, migration 0037).
- `scripts/check_onboarding_links.py`: link-check for the Oracle URLs.

## Non-goals

- The wizard shell and step transitions (#276), real budget-alert check (#279), any OCI API call.
- A nav link (the shell adds `/onboarding/`).

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A tester can sign up from the page alone, and is told up front that the home region (uk-london-1) is permanent | Tests: region warning precedes the steps; moderated dry run is left to the owner |
| O2 | The Pay-As-You-Go 1-2 day delay and "do not wait" appear before the form, and the account shows "upgrade pending" until self-attested active | Content and view tests |
| O3 | Malformed OCIDs and regions are rejected with a message; key/password/token-shaped input is refused, never stored or echoed | Validator table tests, view test |
| O4 | Confirmation is stored per user and resumes; the next step stays locked until the budget alert is acknowledged | View tests (persist, isolation, ready/not-ready) |
| O5 | Every Oracle link resolves, and the page 404s when disabled | `scripts/check_onboarding_links.py` run, 404 test |

## Why

#278 (epic #275), slices S3 and S4 of `specs/onboarding-design.md`: the wizard shell (#276) has a
placeholder access step and no way to learn where the visitor's new Zebra is. The visitor must be
able to grant access with the host holding nothing usable against their tenancy, and the new
instance must be able to tell the host where it is without the host trusting a URL it was handed
(SSRF, session hijack). Also closes the wire-detail gaps listed in #291.

## What Changes

- `onboarding.yaml` v3: `access` (stack or `policy` route), `access_policy` (option B policy text,
  no key upload, `back` route), `provision` (needs a one-time callback token), `await_instance`
  (`external: onboarding_callback`) with `await_instance_retry`; verify shows the verified URL.
- `api/onboarding_access.py`: "Deploy to Oracle Cloud" link from `ONBOARDING_STACK_ZIP_URL`
  (hidden unless https; the #283 zip does not exist yet), optional `ONBOARDING_STACK_ZIP_SHA256`,
  the design's policy text with `<name>` filled in, revoke steps.
- `api/onboarding_callback.py`: token (32 bytes, 1 h, only SHA-256 stored, rotation), lookup by
  hash (cache then RUNNING scan), SSRF-guarded control proof of
  `<instance_url>/.well-known/zebra-onboarding`, compare-and-set used flag, completes the wait.
- Views: `GET /onboarding/revoke/`, `POST /onboarding/token/`, `POST /onboarding/instance/`
  (manual paste), `POST /onboarding/callback/` (CSRF-exempt JSON, 10/min/IP).
- Design §6b documents the step graph and the exact callback contract for #279 S5; the tenancy
  policy line is `manage quota` (OCI's resource type).

## Capabilities

### Modified Capabilities
- `onboarding-access`: access step, policy fallback, revoke screen, callback and control proof.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The default access path stores no tenancy credential: no access/provision form field takes a key, OCID or secret, and the session holds only `__onboarding_cb_sha256__`, `__onboarding_cb_expires__`, `__onboarding_cb_used__` for the token (never the token, which also never reaches a log) | `test_the_access_step_has_no_field_for_a_key_or_secret`, `test_a_token_completes_exactly_one_session`, `test_the_token_never_reaches_a_log` |
| O2 | The access step shows the Deploy to Oracle Cloud link only when `ONBOARDING_STACK_ZIP_URL` is an https URL (empty, http, credentials: hidden); the fallback shows exactly the design's policy text (one compartment block; the two tenancy grants and the runtime dynamic group separate) and states the tenancy-admin requirement from #279 S2 | `test_no_deploy_link_without_an_https_stack_url`, `test_policy_text_is_the_design_text`, `test_policy_fallback_shows_the_policy_for_the_chosen_name`, `test_access_step_hides_the_link_while_no_stack_is_published` |
| O3 | The revoke screen is reachable from every terminal state (finished, ended by failure or expiry, forgotten) and with no session | `test_revoke_*`, `test_the_whole_wizard_finishes` |
| O4 | `POST /onboarding/callback/`: one token completes exactly one session's `await_instance`, also under two concurrent callbacks; a replayed, rotated, unknown or expired token gets 410 and leaves the process properties and task states unchanged; a failed proof returns 422 and leaves the token unused; 400/409/413/429 as documented | `test_onboarding_callback.py` |
| O5 | The control-proof fetch never reaches a non-https, non-443, private, loopback, link-local, CGNAT, multicast or IPv4-mapped/6to4 address (any DNS answer), is pinned to the checked IP (no rebinding), never follows a redirect, and gives up on bodies over 4 KB or after 5 s in total (DNS included) | SSRF tests: the recording transport sees zero requests for refused targets |

## Why

#276 (epic #275): a visitor who wants their own Zebra needs a wizard on a host Zebra. Any Zebra may
host it, including one with real users and data, so it must be safe there by construction: no
accounts, no tables, no secrets (design: `specs/onboarding-design.md`, S1). This change is the shell
and its anonymous, resumable sessions; the access step and callback come in later slices.

## What Changes

- Built-in workflow `onboarding.yaml` (*Onboarding*, `system`): signup → access → provision →
  verify → commons → contribute. Every visitor step is `auto: false` with
  `external: onboarding_visitor` (never in the owner's inbox) and carries what happens / cost /
  undo. A step reported as failed routes to a retry screen showing the reason, then back.
- `zebra_agent_web/api/onboarding.py`: signed resume token `{p, n}` (`django.core.signing`), only
  `sha256(nonce)` stored on the process (`__onboarding_nonce_sha256__`); session load by process id
  only; nonce rotation ("new link") and "forget me"; step view model; step submission (current
  READY visitor task only, known routes only, private keys and API keys refused); launch through
  `create_library_process(entry="onboarding")` of an allowlisted workflow whose library content is
  the shipped built-in, started at once, `user_id` NULL.
- Pages `/onboarding/`, `/onboarding/start/`, `/onboarding/step/`, `/onboarding/r/<token>/`,
  `/onboarding/new-link/`, `/onboarding/forget/` (anonymous, `login_not_required`, exempt from both
  setup middlewares, HTMX step partial). Owner page `/onboarding/manage/` (signed in, owner-only
  POST).
- Switch: `SystemStateModel.onboarding_enabled` (migration 0038, owner toggle) AND
  `ZEBRA_ONBOARDING_ENABLED` (default off). Off: every wizard URL 404s and nothing is created.
- `LAUNCH_ENTRIES` gains `onboarding`.

## Capabilities

### New Capabilities
- `onboarding-wizard`: the anonymous wizard shell, sessions, switch and launch.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Closing the browser mid-wizard and returning (cookie or resume link) resumes at the same step | `tests/e2e/test_onboarding.py`; `test_resume_link_brings_a_new_browser_back_to_the_same_step` |
| O2 | No secret is stored on the session or written to logs: only the nonce hash is stored, private keys are refused, resume tokens and nonces are redacted from every log handler | `test_no_secret_in_properties`, `test_private_keys_are_refused_and_never_stored`, `test_onboarding_token.py` redaction tests |
| O3 | A failed step shows its reason and a retry; later steps stay locked and cannot be completed | `test_a_failed_step_shows_its_reason_and_a_retry_and_locks_later_steps`, e2e |
| O4 | While off (env or owner) every `/onboarding/` URL returns 404 and nothing is created; no wizard path creates a user or lists processes | `test_off_means_404_everywhere`, `test_no_wizard_code_creates_a_user_or_reaches_passkeys`, `test_wizard_views_never_list_processes` |
| O5 | Guardrails (change `onboarding-guardrails`): an over-cap session's LLM call is refused without spending; the 6th session from one IP within an hour gets 429; idle sessions expire | `test_a_session_over_its_cap_fails_its_llm_call_without_spending`, `test_the_sixth_session_from_one_ip_in_an_hour_gets_429`, `test_idle_sessions_expire_and_active_ones_stay` |

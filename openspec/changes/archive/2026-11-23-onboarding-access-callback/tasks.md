> Branch: `f278/onboarding-access-callback` (S3 + S4 of #278). Commits `Part of #278`.

## 1. Workflow

- [x] 1.1 `onboarding.yaml` v3: `access` / `access_policy` / `provision` / `await_instance` (+ retry), `onboarding_panel`, verify shows the instance URL

## 2. Access (S3)

- [x] 2.1 `api/onboarding_access.py`: stack link from `ONBOARDING_STACK_ZIP_URL` (+ SHA-256), policy text, revoke steps
- [x] 2.2 Settings `ONBOARDING_STACK_ZIP_URL`, `ONBOARDING_STACK_ZIP_SHA256`
- [x] 2.3 Templates `partials/panel.html`, `revoke.html`; revoke links on every step and terminal state

## 3. Callback (S4)

- [x] 3.1 `api/onboarding_callback.py`: token issue/rotate, lookup, SSRF-guarded proof, compare-and-set, completion
- [x] 3.2 Views and URLs: `revoke/`, `token/`, `instance/`, `callback/`
- [x] 3.3 Wizard: waiting state shows the await panel; problem route from the wait; provision needs a token

## 4. Tests and docs

- [x] 4.1 `test_onboarding_access.py`, `test_onboarding_callback.py` (SSRF cases), updated shell tests
- [x] 4.2 Design §6b (step graph, callback contract for #279 S5), as-is, AGENTS.md rows

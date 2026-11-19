> Branch: `f276/onboarding-wizard-shell` (S1 + S2 of #276). Commits `Part of #276`; the merge closes #276.

## 1. Workflow and launch

- [x] 1.1 `zebra-agent/workflows/onboarding.yaml`: six visitor steps (external waits) with what / cost / undo, retry tasks, `system` tag
- [x] 1.2 `LAUNCH_ENTRIES` gains `onboarding`
- [x] 1.3 `api/onboarding.py`: allowlist, built-in hash check, `start_session` (no user, started at once)

## 2. Sessions

- [x] 2.1 Signed token, nonce hash only, `load_session` by id, `rotate_nonce`, `forget_session`
- [x] 2.2 `wizard_state` (own process only) and `submit_step` (current task, known routes, private material refused)

## 3. Web

- [x] 3.1 `SystemStateModel.onboarding_enabled` + migration 0038; `ZEBRA_ONBOARDING_ENABLED` setting
- [x] 3.2 Views, URLs, middleware exemptions, templates (`onboarding/wizard.html`, `partials/step.html`, `manage.html`), owner nav link

## 4. Tests

- [x] 4.1 `test_onboarding_token.py`, `test_onboarding_launch.py`, `test_onboarding_wizard_views.py`
- [x] 4.2 `tests/e2e/test_onboarding.py`

## 5. Docs

- [x] 5.1 `specs/onboarding-design.md` (as built), `specs/zebra-as-is.md`, package AGENTS.md, CLAUDE.md settings
- [x] 5.2 Issue #276 body brought in line with the design

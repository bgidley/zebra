## 1. Branch Setup

- [x] 1.1 Create feature branch `f19/ethics-gate-values-profile` from master

## 2. EthicsGateAction — Values Integration

- [x] 2.1 Add `user_id` optional input parameter to `EthicsGateAction.inputs`
- [x] 2.2 Write `_load_profile_text(user_id, context)` helper — loads profile via `__profile_store__`, returns `dict | None`; logs warning if store absent, INFO if no profile found
- [x] 2.3 Write `_build_values_system_prompt(base_prompt, profile)` — wraps profile fields in XML-like delimiters and appends a values-alignment section to the Kantian system prompt; truncates each field to 300 chars
- [x] 2.4 Update `EthicsGateAction.run()` to load profile when `user_id` present, select combined vs Kantian-only system prompt, and pass both prompts to existing LLM call
- [x] 2.5 Update LLM response parsing to extract `values_assessment` from JSON; default to `null` when absent (Kantian-only path)
- [x] 2.6 Apply precedence rule: `approved = kantian_approved and (values_approved if profile_loaded else True)`; overwrite top-level `"approved"` in the assessment dict before storing
- [x] 2.7 Update log line to include values verdict when profile was loaded

## 3. Tests

- [x] 3.1 Add test: gate with `user_id` + profile present — LLM prompt includes profile text
- [x] 3.2 Add test: Kantian rejects, values approves → final `approved=False`, `next_route="reject"`
- [x] 3.3 Add test: Kantian approves, values rejects → final `approved=False`, `next_route="reject"`
- [x] 3.4 Add test: both approve → final `approved=True`, `next_route="proceed"`
- [x] 3.5 Add test: gate with `user_id` but no profile store → Kantian-only path, no crash
- [x] 3.6 Add test: gate with `user_id` but `get_current()` returns `None` → Kantian-only path
- [x] 3.7 Add test: stored assessment contains `values_assessment: null` on Kantian-only path
- [x] 3.8 Add test: stored assessment contains `values_assessment` dict with `approved/reasoning/conflicts` when profile loaded

## 4. Spec Update

- [x] 4.1 Update `specs/zebra-as-is.md` to note that `EthicsGateAction` now accepts an optional `user_id` and can consult the values profile

## 5. Lint, Tests, and Commit

- [x] 5.1 Run `uv run ruff check --fix . && uv run ruff format .`
- [x] 5.2 Run `uv run pytest zebra-tasks/tests/test_ethics_gate.py -v` — all tests green
- [x] 5.3 Run `uv run pytest` — full suite green
- [ ] 5.4 Commit: `feat: extend ethics gate with optional values-profile consultation — Closes #19`
- [ ] 5.5 Push to GitLab, watch CI pipeline (`lint → unit → e2e` green)
- [ ] 5.6 Push branch to GitHub and open PR against master

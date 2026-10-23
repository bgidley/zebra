## 1. Prod checks (read-only)

- [x] 1.1 #200: Dream Cycles since the #195 deploy store an `evaluation` without `parse_failure`
- [x] 1.2 #199: prod postmortems exist with embeddings; find why none has trigger `failure`
- [x] 1.3 #218: find why logged-in smoke tests skip (no `ZEBRA_SMOKE_SESSION` in CI)

Not in this change: #210's prod run (queue a goal with a stored legacy `__llm_model__`) writes
to prod and is left for the human to approve; #210 stays open.

## 2. Smoke login

- [x] 2.1 `manage.py smoke_session` + unit tests
- [x] 2.2 `smoke` CI job exports `ZEBRA_SMOKE_SESSION`
- [x] 2.3 Smoke tests for `/tasks/` and `/nav/needs-you/`; dashboard not redirected to login

## 3. Postmortem trigger

- [x] 3.1 `unreflected_trigger()` in `zebra_agent/postmortem.py`; `postmortem_failed_goal` uses it
- [x] 3.2 Tests: crash → `failure`, timeout errors → `timeout`

## 4. Test gaps

- [x] 4.1 READY auto task is not in the inbox
- [x] 4.2 Evaluator parses an unclosed-fence reply in one call

## 5. Docs

- [x] 5.1 `specs/zebra-as-is.md`, `README-CICD.md`, package AGENTS.md

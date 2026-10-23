## Why

Four outcome-review follow-ups asked for proof on prod that was never collected (#218, #210, #199,
#200). Checking prod found two real gaps behind them:

- **The logged-in smoke tests never run.** `test_dashboard_accessible` and `test_budget_api` skip
  on every deploy because nothing sets `ZEBRA_SMOKE_SESSION` (login is passkey-only). Adding
  `/tasks/` to them, as #218 asks, would add one more skip.
- **Crashed goals are journalled as timeouts.** `postmortem_failed_goal` hard-codes trigger
  `timeout`. The only failed goal since #175 (run `42d9c1a2`, 2026-10-20, "Failed to parse LLM
  response as JSON") got a `timeout` postmortem, so #199's "row with trigger `failure`" can
  never appear for a goal that crashes before reflecting.

The rest is verified on prod already: four Dream Cycles since #195 (2026-10-20 to 23) stored an
`evaluation` with no `parse_failure` (#200 part 1); both prod postmortems have embeddings (#199).
Closes #218, closes #199, closes #200. Refs #210.

## What Changes

- **`manage.py smoke_session`**: prints a 15-minute session key for the `smoke` user (exit 1 if
  missing/inactive). The `smoke` CI job exports it as `ZEBRA_SMOKE_SESSION`, so logged-in smoke
  tests run.
- **Smoke tests** for `/tasks/` (inbox or empty state, no error, not the login page) and
  `/nav/needs-you/`; the dashboard test also checks it was not redirected to login.
- **Unreflected postmortem trigger**: `unreflected_trigger(error)` gives `timeout` when the error
  says it timed out ("Timed out after Ns", "Agent loop timed out"), else `failure`.
- **Tests**: a READY auto task is left out of the inbox (#218); the evaluator parses a reply in
  an unclosed fence in one call (#200).

## Non-goals

- #210's prod run (a queued goal with a stored legacy `__llm_model__`): it writes to prod, so it
  is left for the human to approve. `normalize_model` is already unit-tested.
- Browser (Playwright) smoke of the inbox: HTTP-level checks of the rendered markup suffice.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Logged-in pages are smoke-tested on every deploy | The master pipeline's `smoke` job log shows `test_dashboard_accessible`, `test_budget_api`, `test_tasks_inbox` and `test_needs_you_badge` PASSED, none SKIPPED |
| O2 | `smoke_session` gives a working, short-lived login | Unit tests: the key authenticates as `smoke` on `/tasks/` and `/nav/needs-you/`, expires in the given minutes (default 15), and a missing or inactive user fails; the key never appears in the `smoke` job log |
| O3 | A crashed goal's postmortem says `failure`; a timed-out one says `timeout` | Unit tests: the prod parse-error case stores trigger `failure`; "Timed out after 900.0s" / "Agent loop timed out" give `timeout`; existing timeout test still passes |
| O4 | A READY auto task stays out of the inbox, and an unclosed-fence evaluator reply parses in one call | Unit tests: a READY auto task is not in the inbox; the evaluator parses an unclosed-fence reply with one LLM call and no `parse_failure` |

Zebra's outcome feedback (advisory): O2 and O4 tightened as suggested. Not taken: making smoke
block the deploy. Smoke runs after deploy by design (the deploy has its own health-gated
rollback); gating is out of scope here.

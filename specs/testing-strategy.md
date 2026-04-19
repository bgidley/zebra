# Zebra Testing Strategy

**Status:** Draft
**Last updated:** 2026-04-17

## Philosophy

Zebra is designed to **self-evolve**: workflows, memory, prompts, and eventually the action catalogue change over time without direct human authorship. Tests that pin internal behaviour (exact prompts, specific task sequences, intermediate state shapes, precise cost numbers) will decay into churn and, worse, will *discourage* the very evolution the system is built for.

We therefore invert the usual test pyramid:

- **Primary layer — end-to-end, black-box tests through a single UX.** These describe what the system does for a user, not how it does it.
- **Thin support layer — narrow unit tests only where a contract is genuinely load-bearing** (state machine transitions, serialisation round-trips, security boundaries, public SDK surfaces).
- **No middle layer of integration tests that reach into internals.** If a test needs to mock an LLM provider to assert a specific prompt or assert a specific task was scheduled in a specific order, it is working against the design.

The rule of thumb: **if a test would fail when the agent learns a better way to achieve the same outcome, it is the wrong test.**

## The "main" UX under test

Zebra currently exposes several surfaces (CLI, Python SDK, web UI, MCP server). Maintaining full E2E suites against all of them is a losing battle. We pick **one canonical UX** and treat it as the system-under-test:

**Chosen UX: the Django web application in [`zebra-agent-web/`](../zebra-agent-web/).**

Rationale:

- It is the richest surface — goal submission, human tasks, activity, budget, workflow library, diagrams — so it exercises the most of the engine per test.
- It exposes both HTML and JSON endpoints, so a single driver can assert on either.
- It is the surface users actually interact with; regressions here are the ones that matter.
- The other surfaces (CLI, MCP, SDK) are thin adapters over the same engine; if the web UX is healthy, regressions in the adapters are almost always in the adapter code itself and are cheap to catch with a handful of smoke tests per adapter.

Other UX surfaces get **smoke tests only** (one or two happy-path invocations per surface), not a full E2E suite.

## What an E2E test looks like

An E2E test:

1. Boots the Django app (in-process test client or a real Daphne instance) against a **real** workflow engine, **real** state store (SQLite is acceptable for CI; Oracle for the nightly suite), and a **recorded or stubbed** LLM provider.
2. Drives the system through HTTP (and WebSocket where relevant) — the same entry points a human or external caller uses.
3. Asserts only on **observable outcomes** visible through the UX: response status, rendered page content, API payload shape, final run state (success/failure), human-task availability, cost appearing on the activity page, kill-switch taking effect, etc.
4. Does **not** assert on: which workflow was chosen, which tasks ran in which order, prompt contents, intermediate process properties, or the internal structure of the state store.

### Example shapes

- **Goal submission happy path** — POST a goal, poll `/runs/<id>/` until it reports `complete` or `failed`, assert it completed and produced some output. No assertions about which tasks ran.
- **Human task loop** — submit a goal known to require human input, poll `/tasks/` until a task appears, fetch its schema via `/api/processes/<id>/pending-tasks/`, POST an answer to `/api/tasks/<id>/complete/`, assert the run then progresses.
- **Budget gate** — set `DAILY_BUDGET_USD` very low, queue goals, assert that once budget is exhausted no further goals enter `RUNNING`, and that `/api/budget/` reports the exhausted state.
- **Kill switch** (REQ-TRUST-007) — hit the kill endpoint mid-run, assert the run reaches a terminal `failed`/`stopped` state within a bounded time and no further tasks execute.
- **Workflow evolution resilience** — run the same goal twice with a deliberately different workflow library between runs; both should succeed, even though the path taken differs.

## LLM handling in tests

LLM calls are the primary source of non-determinism and cost. Options, in order of preference:

1. **Recorded-cassette mode** (preferred for CI) — use a recording proxy (VCR-style) that captures real provider responses once per goal, then replays them. New scenarios require a one-time record run with a real key; the recording is checked in.
2. **Stub provider** (for scenarios where we only care about shape, not content) — a deterministic stub that returns canned responses keyed by a rough prompt shape. Never assert on prompt contents.
3. **Real provider** (nightly / release only) — small number of scenarios run end-to-end against the real Anthropic API to catch drift.

Cost assertions use coarse bounds (`cost > 0`, `cost < daily_budget`), never exact figures.

## What we *do* still unit-test

Narrow, high-value contracts where wrong behaviour is catastrophic and the contract is genuinely stable:

- **State machine legality** — process/task state transitions in `zebra-py` (e.g. `READY → RUNNING → COMPLETE`). These are invariants, not implementation details.
- **Serialisation** — `TaskResult`, `ProcessInstance`, and properties must round-trip through JSON without loss; non-serialisable values must be rejected.
- **Security boundaries** — anything touching credentials, permissions, or the kill switch.
- **Public SDK surface** — the few functions/classes external callers depend on (engine construction, `create_process`, `start_process`, `complete_task`).
- **Pure utilities** — `zebra.forms` schema→form conversion, routing condition evaluation, template rendering helpers — where the input/output is a pure function.

Everything else — task action internals, prompt building, memory retrieval strategies, workflow selection — is considered **free to evolve** and is exercised only via E2E.

## What we explicitly **do not** test

- Which workflow is chosen for a given goal.
- Which tasks a workflow contains or their order.
- Exact prompt text or LLM response content.
- Exact token counts or cost figures.
- Internal shapes of process properties or `__task_output_*` keys.
- Memory store contents after a run (beyond "something was written" smoke checks where REQ demands it).
- Diagram SVG byte content (assert renders without error, not visual identity).

If a reviewer sees a test asserting any of the above, the default action is to delete it or rewrite it as a UX-level observable assertion.

## Test organisation

This section describes the **target** layout. Today every package uses a flat `tests/` directory (`zebra-py/tests/`, `zebra-agent/tests/`, `zebra-agent-web/tests/`, `zebra-tasks/tests/`) with no layer separation.

**Target layout:**

| Layer | Location | Runs in CI | Cadence |
|-------|----------|------------|---------|
| E2E (web UX, cassette LLM, SQLite) | `zebra-agent-web/tests/e2e/` | Yes | Every PR |
| E2E (web UX, real LLM, Oracle) | `zebra-agent-web/tests/e2e_live/` | Optional | Nightly + pre-release |
| Smoke (CLI, MCP, SDK adapters) | per-package `tests/smoke/` | Yes | Every PR |
| Narrow unit tests | per-package `tests/unit/` | Yes | Every PR |

Nightly/live runs are allowed to be flaky-tolerant (retry once); PR-gating tests must be deterministic.

**CI host:** GitLab ([`.gitlab-ci.yml`](../.gitlab-ci.yml)) driving a self-hosted runner on the Oracle VM (shell executor, Podman for deploy). The nightly real-LLM run is a GitLab Pipeline Schedule, not a cron expression in YAML. See [`deploy/gitlab-runner-bootstrap.md`](../deploy/gitlab-runner-bootstrap.md).

**Migration path** (tracked as feature F1 in [../plan/backlog.md](../plan/backlog.md)):

1. Create the `e2e/`, `smoke/`, `unit/` subdirectories per package and wire up `pytest` markers (`@pytest.mark.e2e`, `@pytest.mark.smoke`, `@pytest.mark.unit`) so CI can select layers.
2. Triage existing tests against the "What we do still unit-test" and "What we explicitly do not test" lists in this doc. For each existing test, either:
   - Move it into `unit/` if it covers a load-bearing stable contract, or
   - Rewrite it as an E2E scenario in `zebra-agent-web/tests/e2e/` if it was reaching into internals to verify user-visible behaviour, or
   - **Delete it** if it only pins behaviour this strategy says should be free to evolve.
3. Stand up the first cassette-based E2E scenario (goal happy path) as the template for the rest.
4. Only once the E2E layer is green on every PR, start trimming the legacy tests flagged for deletion.

Expect the "delete" pile to be substantial — that is the point, not a concern.

## Writing a new test — decision guide

1. **Is there a user-visible behaviour change?** Add or extend an E2E scenario in `zebra-agent-web/tests/e2e/`.
2. **Is there a new stable contract** (state transition, serialisation, security check, public API)? Add a narrow unit test.
3. **Anything else?** Don't add a test. The E2E suite will catch regressions that matter; anything it doesn't catch is behaviour we have explicitly decided should be free to evolve.

If in doubt, prefer fewer tests that each describe a user journey over many tests that each pin an implementation detail.

## Open questions

- Which E2E driver? Django `Client` is sufficient for HTML/JSON; for WebSocket-driven features (goal progress) we likely need `pytest-asyncio` + Channels' `WebsocketCommunicator`, or a headless browser (Playwright) if we want to exercise the live diagram.
- Cassette tooling: VCR.py vs. a bespoke recorder that understands streaming responses. TBD.
- How to seed the workflow library deterministically for E2E without freezing its content — probably a fixture that provides *a* library meeting shape requirements, not *the* current library.

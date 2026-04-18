# Zebra Feature Backlog — Path to Requirements

## Context

The Zebra workflow engine has a solid core (engine, FOE, storage abstraction, IoC, agent main loop, web UI with daemon) but is pre-multi-user and missing large chunks of the vision: no trust model, no values profile, no knowledge store, no proactive agent, no event bus / scheduler beyond the budget daemon, no MCP server, thin auth, and fragile test coverage on the web layer.

`docs/requirements.md` catalogues 75 requirements (49 P1, 20 P2, 6 P3). `specs/testing-strategy.md` (just drafted) proposes an **inverted pyramid** — the Django web UI is the canonical black box under test; narrow unit tests only for load-bearing contracts. `specs/distributed-data-model.md` sketches the Phase 2–3 CRDT/relay sync path.

This plan turns that into a sequenced, deliverable backlog. Each feature is a **thin vertical slice** (1–3 days) that leaves the system runnable and testable end-to-end. **Feature 1 must be the testing baseline** — every feature after it is validated via the canonical E2E harness it puts in place.

Ordering rule after F1: **user-visible value first**. Infrastructure items are pulled in only when they unblock the next visible feature.

Phases 1–11 are ordered by user-visible value. Phases 12–16 are **enabler tracks** — their items are pulled forward into earlier phases whenever a user-visible feature depends on them (e.g. a scheduling domain in Phase 9 will likely pull in HTTP/calendar actions from Phase 12).

## Conventions for every feature

- **Definition of Done**:
  1. Requirement(s) addressed, linked by REQ-ID
  2. E2E test(s) through the Django UI (or relevant interface) added to the canonical harness — per `specs/testing-strategy.md`
  3. Narrow unit tests for any new contract (state legality, serialisation, public SDK surface)
  4. `uv run pytest` green; `uv run ruff check .` clean
  5. System bootable end-to-end — `manage.py run_daemon` starts, goal can be submitted
  6. `specs/` updated (as-is, module spec, or new doc) and `AGENTS.md` index refreshed
  7. One-paragraph changelog entry under `docs/` (or equivalent)
- **Test cassettes**: all LLM calls in CI use recorded cassettes. Real-LLM run gated to nightly.
- **Migrations**: every schema change ships with forward migration + backfill. No destructive migrations without user sign-off.

---

## Phase 0 — Testing Baseline (mandatory first)

### F1. Canonical test harness for what exists today
**Outcome**: CI green on every PR, E2E tests exercise the Django UI end-to-end using recorded LLM cassettes, regression signal before any new feature lands.

Scope:
- Set up `.github/workflows/ci.yml`: `uv sync --all-packages`, `ruff check`, `ruff format --check`, `pytest` on SQLite.
- Add `tests/e2e/` in `zebra-agent-web/` using Django test client + channels test client.
  - Golden-path goal flow: submit → daemon picks up → workflow runs → cost appears → completion.
  - Human task loop: goal pauses on `auto:false` task → form schema exposed → submit form → workflow resumes.
  - Budget exhaustion: daemon pauses new goals when daily budget hit; soft warning visible.
  - Workflow diagram SVG renders for a completed run.
  - Daemon auto-start on first web request.
- Add LLM cassette layer. Prefer `vcrpy`-style tape or a bespoke recorder wrapping `zebra_tasks.llm.providers`. Record against real Anthropic once; replay deterministically in CI.
- Backfill narrow unit tests for contracts called out in `specs/testing-strategy.md`:
  - Process/task state-machine legality (`zebra-py/zebra/core/models.py`, engine transitions).
  - `TaskResult` / process property JSON round-trip.
  - `WorkflowEngine.create_process` / `start_process` / `complete_task` public signatures.
  - `forms.py` `schema_to_form` / `coerce_form_data` / `validate_form_data`.
- Gap-fill coverage for currently-untested modules: `zebra_tasks.consult_memory`, `update_conceptual_memory`, `analyze`, `evaluator`, `optimizer`, `variant_creator`, `python_exec`, `assess_and_record`.
- Add nightly CI job (or label-triggered) that runs the E2E suite against real Anthropic + Postgres.
- Document running the suite in `specs/testing-strategy.md` (commands, cassette refresh workflow, how to extend).

Critical files: new `.github/workflows/ci.yml`; new `zebra-agent-web/tests/e2e/`; extend `zebra-agent-web/conftest.py`; new cassette helper under `zebra-tasks/zebra_tasks/llm/_testing.py`; update `specs/testing-strategy.md`.

---

## Phase 1 — Safety & identity foundation (visible: agent is safe, is *mine*)

### F2. Kill switch (REQ-TRUST-007)
One-click web endpoint + CLI command that halts every process outside the engine. Persisted "halted" flag blocks daemon pickup. E2E test: submit goal, hit kill switch, verify no new processes start and in-flight tasks stop at next checkpoint.

### F3. Observability baseline (REQ-NFR-004)
`/health` endpoint, structured JSON logging (`structlog`), request/task metrics exposed at `/metrics` (Prometheus text). Correlation ID per process. E2E test asserts /health, /metrics present; asserts correlation ID propagates from web request through daemon to task log.

### F4. Single-user bound identity (REQ-USR-001)
First-run setup flow captures user's display name + generates local identity. Stored in settings store. Every process/run stamped with this identity. E2E: fresh install → setup page → identity persists → appears on dashboard.

### F5. Web authentication (enables REQ-USR-001, REQ-NFR-007)
Django auth (passkey or password) on all web endpoints including daemon-facing URLs. Redirect to setup when no user exists. E2E: unauth request → redirect; auth → dashboard.

### F6. user_id namespacing across stores (REQ-USR-002)
Add `user_id` column to processes, tasks, memory, metrics, knowledge. Forward migration backfills single-user id. Store interfaces take `user_id` and enforce scope. E2E: two users' data isolated (second user added via management command for test).

### F7. OS keychain credential store (REQ-DATA-006, REQ-INT-002)
Replace `.env`-based secret handling with keychain-backed store (macOS Keychain, Secret Service on Linux, file+OS-perm fallback). Credentials never logged. E2E: set credential via CLI, daemon reads it, log scrape shows no secret.

### F8. Crash recovery contract (REQ-NFR-002)
Formalise write-ahead: every state transition is persisted before the in-memory event fires. Add recovery test that kills the daemon mid-task and asserts resume on restart. Already largely true — this feature adds the test matrix and closes any gaps found.

### F9. Data export (REQ-DATA-003)
`zebra export --user <id> --out zebra-export.zip` produces portable JSON + YAML bundle (processes, memory, metrics, knowledge, workflows). Web UI has an export button. E2E: export, fresh instance, re-import (deferred), verify file content.

### F10. Data deletion (REQ-DATA-005)
"Delete my data" flow removes everything user-scoped, local-immediate. Management command equivalent. E2E: create run, delete, verify nothing left.

### F11. Context minimisation / memory tiers (REQ-DATA-004)
Enforce tiered retention: hot (full), warm (summarised), cold (metadata only). Scheduled compaction job. E2E: seed old runs → trigger compaction → verify retention.

---

## Phase 2 — Trust model (visible: agent asks permission appropriately)

### F12. Trust level data model (REQ-TRUST-001)
Per-domain trust levels (SUPERVISED / SEMI-AUTONOMOUS / AUTONOMOUS). Domain taxonomy registry. Default SUPERVISED for all. Dashboard shows trust by domain.

### F13. `trust_gate` task action (REQ-TRUST-003)
New action in `zebra-tasks` that pauses workflow for human approval when required trust isn't met. Re-uses `auto:false` pattern. E2E: workflow with trust_gate pauses, human approves, resumes.

### F14. Contextual reversibility assessment (REQ-TRUST-002)
Per-action metadata + runtime context assessor returns `reversible | recoverable | irreversible`. Feeds trust_gate decision. E2E: file delete classified irreversible under a certain path prefix, forces gate.

### F15. Human-only trust promotion/demotion (REQ-TRUST-004)
UI + API for user to change domain trust level. Agent can only *request* promotion via a queued suggestion — never self-promote. Audit log of changes. E2E: agent-submitted promotion appears as pending suggestion, user approves, level changes.

### F16. Emergency override (REQ-TRUST-005)
One-click "revert all domains to SUPERVISED". Kill-switch sibling. E2E: after override, previously-AUTO workflow requires approval on next step.

### F17. Freeing Zebra (REQ-TRUST-006)
Irreversible flow: user promotes all domains to AUTONOMOUS permanently, all trust gates disabled. Requires double confirmation + 24h cooling-off. E2E: confirm flow, verify gates bypassed, verify cannot reverse.

---

## Phase 3 — Values & ethics (visible: agent reflects my values)

### F18. Values profile (REQ-ETH-002)
Data model: core values, ethical positions, deal-breakers. Wizard UI for initial capture + edit. Stored per user.

### F19. Values-informed reasoning with Kantian precedence (REQ-ETH-003, REQ-ETH-001, REQ-PRIN-004)
Extend existing `ethics_gate` to load values profile, combine with Kantian evaluator; Kantian result wins ties. E2E: workflow with ethics_gate consults profile; log shows reasoning.

### F20. Ethics audit trail (REQ-ETH-006)
Every ethics evaluation appended to immutable audit log; viewable in UI, exportable. E2E: run workflow, see audit entries.

### F21. Proactive concern flagging (REQ-ETH-004)
Agent flags potential concerns during planning, before formal gates. Surfaced in run detail. E2E: workflow where plan contains risky step → concern entry appears.

### F22. Dilemma escalation (REQ-ETH-005)
When Kantian + values conflict, or multiple values conflict, pause and escalate to user. UI shows both sides. E2E: triggered dilemma produces pause + resolution UI.

---

## Phase 4 — Peer relationship (visible: feels like a peer, not a tool)

### F23. Transparent reasoning surface (REQ-PEER-002)
Run detail view shows reasoning for each task's output (already partially there). Explicit "why did you do that?" button queries stored rationale. E2E: asserts rationale present for each task.

### F24. Personality config + consistency (REQ-PEER-005)
Single personality prompt fragment injected into every LLM call. Configurable. E2E: verify same opening style across two different workflows.

### F25. Respectful pushback + 2-round protocol (REQ-PEER-003, REQ-PEER-004)
Agent can disagree with user instruction once, explain, on second instruction defer and execute. New workflow pattern. E2E: submit instruction that conflicts with values → agent pushes back → resubmit → agent executes.

### F26. Long-term relationship memory (REQ-PEER-006)
Milestones store (anniversaries, preferences learned, achievements). Surfaced contextually in goal drafting. E2E: seed milestone → agent references it in response.

---

## Phase 5 — Proactivity (visible: agent moves on its own)

### F27. Polling scheduler (REQ-PRIN-008)
Cron-style routine definitions (`routines/*.yaml`). Daemon evaluates at tick. Re-uses budget daemon loop. E2E: routine scheduled for 1-minute interval fires in test clock.

### F28. Event-driven trigger bus (REQ-PRIN-009)
Pub/sub in-process bus + external event intake (webhook endpoint). Triggers subscribe to events → start workflows. E2E: POST webhook → workflow starts.

### F29. Agent proposes goals (REQ-PEER-001, REQ-PRIN-006)
Observer workflow runs on schedule, proposes goals as queued items with rationale. User approves → executed. E2E: seed observable state → proposal appears → approve → runs.

### F30. Notification system + quiet hours (REQ-UI-004)
Pluggable channels (inline dashboard, OS notification, email, webhook). Quiet-hours policy. E2E: notification queued during quiet hours delivered after.

---

## Phase 6 — Knowledge depth (visible: agent knows about me)

### F31. Personal knowledge store (REQ-MEM-004)
Typed, categorised knowledge entries scoped to user + domain. CRUD UI. Agent reads during planning. E2E: add entry → agent uses it in goal.

### F32. Knowledge lifecycle (REQ-MEM-005)
Verification status, decay half-life per type, contradiction detection + escalation. E2E: contradicting entry triggers dilemma.

### F33. Cross-domain memory privacy (REQ-MEM-006)
Domain membranes — explicit grants for cross-domain reads. E2E: health domain cannot read finance unless granted.

---

## Phase 7 — Interfaces (visible: I can reach the agent everywhere)

### F34. CLI with persistent store (REQ-UI-003)
`zebra` CLI uses same storage as web (SQLite default). E2E: goal created via CLI appears in web dashboard.

### F35. Chat interface (REQ-UI-002)
Natural-language entry → goal; structured inline elements (forms, confirmations, diagrams). Re-uses E2E goal flow.

### F36. Dashboard refinements + consistency (REQ-UI-001, REQ-UI-005)
Golden-path parity across web/chat/CLI; single component library for structured elements. E2E: same goal listed identically in all three.

---

## Phase 8 — Integrations & plugins (visible: agent touches my tools)

### F37. Integration provider interface (REQ-INT-001)
Abstract `IntegrationProvider` with standard lifecycle (connect, health, invoke, disconnect). Registered via entry point. E2E: sample "echo" provider wired end-to-end.

### F38. MCP server (REQ-INT-003)
Implement the currently-missing `zebra-py/zebra/mcp/` surface. Agent exposes selected workflows as MCP tools. E2E via MCP client.

### F39. Integration health monitoring (REQ-INT-004)
Periodic health checks; failure state + retry policy; dashboard tile. E2E: killed provider reported unhealthy.

### F40. Plugin entry-point docs + samples (REQ-PRIN-002)
Mostly in place. This feature hardens and documents the pattern; adds contract tests; writes `docs/plugin-authoring.md`.

### F41. Workflow sharing with ethics review (REQ-PRIN-007)
Export/import workflow bundle; import triggers ethics review workflow before activation. E2E: import workflow → ethics review runs → workflow available after approval.

---

## Phase 9 — Domains (visible: daily helpfulness)

Each domain is one feature unless noted. Pattern: domain plugin (entry-point), data model, at least one end-to-end workflow, trust integration, E2E test.

- **F42.** Code domain — verify preservation + trust integration (REQ-DOM-CODE-001, REQ-DOM-CODE-002).
- **F43.** Scheduling — calendar awareness, timezone, working hours (REQ-DOM-SCHED-001).
- **F44.** Scheduling — event CRUD + conflict detection (REQ-DOM-SCHED-002).
- **F45.** Scheduling — routine detection & optimisation (REQ-DOM-SCHED-003).
- **F46.** Research — workflows, summaries, sources (REQ-DOM-RESEARCH-001).
- **F47.** Research — topic monitoring + relevance alerts (REQ-DOM-RESEARCH-002).
- **F48.** Finance — balances/transactions awareness, local-only (REQ-DOM-FIN-001).
- **F49.** Finance — budget tracking + overspend alerts (REQ-DOM-FIN-002).
- **F50.** Health — tracking, fitness data, highest-privacy (REQ-DOM-HEALTH-001).
- **F51.** Health — wellness nudges (REQ-DOM-HEALTH-002).
- **F52.** Home — recurring chores + supplies (REQ-DOM-HOME-001).
- **F53.** Creative — milestones, inspiration, autonomy (REQ-DOM-CREATIVE-001).
- **F54.** Social — relationship maintenance, dates, drafting (REQ-DOM-SOCIAL-001).

---

## Phase 10 — Non-functional targets (visible: agent is fast + scales)

### F55. Response time SLIs (REQ-NFR-001)
Instrument init, goal create, dashboard latency. Gate PRs on regression. Budget controls per domain (REQ-NFR-003) layered here — per-domain spend limits and soft warnings.

### F56. Scalability targets (REQ-NFR-006)
Benchmark to 100k knowledge entries, 10k episodic runs; add indices where needed. Nightly load test.

---

## Phase 11 — Distributed & multi-user (specs/distributed-data-model.md)

### F57. cr-sqlite integration, single-user multi-device (REQ-DATA-001 upgrade, REQ-NFR-005)
Swap SQLite for cr-sqlite; add CRDT metadata columns; offline queue. E2E: two devices same user sync after reconnect.

### F58. Encrypted cloud relay (REQ-DATA-002)
Relay server for encrypted changeset forwarding; client-side keys. E2E: two offline devices sync via relay.

### F59. Family/household multi-user (REQ-USR-003)
Keypair generation, capability tokens, shared vs private domains. E2E: two users in household, shared calendar visible, private finance isolated.

### F60. Multi-user conflict resolution (REQ-USR-005)
Agent acts as impartial mediator when values conflict across users. E2E: household scheduling conflict → mediation proposal.

### F61. Team/organisation support (REQ-USR-004)
Role-based access, org policy layer over capabilities. E2E: role-based visibility on shared workflows.

---

## Critical files (reference)

- Engine & state machine: `zebra-py/zebra/core/engine.py`, `zebra-py/zebra/core/models.py`
- Storage interfaces: `zebra-py/zebra/storage/*.py`
- Agent loop: `zebra-agent/zebra_agent/loop.py`, `zebra-agent/workflows/agent_main_loop.yaml`
- IoC: `zebra-agent/zebra_agent/ioc/*.py`
- LLM + cost: `zebra-tasks/zebra_tasks/llm/`, `zebra-tasks/zebra_tasks/llm/_pricing.py`
- Ethics: `zebra-tasks/zebra_tasks/agent/ethics_gate.py`
- Web entry: `zebra-agent-web/api/`, `zebra-agent-web/asgi.py`, `zebra-agent-web/api/daemon.py`
- Docs: `docs/requirements.md`, `specs/testing-strategy.md`, `specs/distributed-data-model.md`, `specs/zebra-as-is.md`

## Verification (plan-level)

After F1 ships:
- `uv run pytest` green locally and on GitHub Actions CI.
- Nightly job runs the same E2E suite against real Anthropic + Postgres.
- Any future feature lands with ≥1 E2E test extending the canonical harness — otherwise not done.

After every subsequent feature:
- Boot: `uv run uvicorn zebra_agent_web.asgi:application` → dashboard loads.
- Submit a goal end-to-end, confirm the new capability is exercised.
- Review `specs/` diff to confirm docs kept in sync.

## Out of scope for this plan

- Detailed technical design inside each feature — produced per-feature via separate plan mode sessions.
- Prioritising P2/P3 above P1 within a phase: the P1-flagged items lead each phase.
- Rewrites of existing working modules (engine, FOE, IoC) — refactor only when a feature requires it.

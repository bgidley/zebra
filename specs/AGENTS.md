# Specs Directory Index

This directory contains requirements and design specifications for Zebra.

## Documents

| File | Purpose | Status |
|------|---------|--------|
| [zebra-as-is.md](zebra-as-is.md) | Snapshot of the current implementation: architectural layers, per-package capabilities, strengths, weaknesses, gaps vs. requirements | Current |
| [zebra-to-be.md](zebra-to-be.md) | High-level technical design for the target system: subsystems, interfaces, migration path, risks | Draft |
| [distributed-data-model.md](distributed-data-model.md) | #57–#61: multi-device and multi-user on one server + Oracle schema: devices are clients, members/roles, `private` vs `shared:<domain>` row scope enforced fail-closed in the stores, fair-share budget, conflict mediation as a workflow; supersedes the April 2026 local-first cr-sqlite/CRDT draft | Draft |
| [testing-strategy.md](testing-strategy.md) | Testing philosophy: E2E black-box through the web UX as primary layer, narrow units only for stable contracts | Draft |
| [f2-kill-switch.md](f2-kill-switch.md) | F2: Kill switch — `SystemStateModel`, daemon halted flag, web endpoint, management command | Implemented |
| [f3-observability.md](f3-observability.md) | F3: Observability — structlog JSON logging, Prometheus `/metrics`, `/health` endpoint, partial correlation ID | Implemented |
| [f4-f5-identity-auth.md](f4-f5-identity-auth.md) | F4+F5: Single-user identity setup flow + passkey (WebAuthn) web authentication | Implemented |
| [f6-user-id-namespacing.md](f6-user-id-namespacing.md) | F6: user_id columns on all Django store tables, `CurrentUserMiddleware` ContextVar propagation | Implemented |
| [f7-credential-store.md](f7-credential-store.md) | F7: OS keychain credential store — `CredentialStore` ABC, keyring + file backends, CLI commands | Implemented |
| [f8-crash-recovery.md](f8-crash-recovery.md) | F8: Crash recovery contract — write-ahead guarantees, daemon startup `resume_all_processes` (background, children-first), resumable goal execution (#129); manual-review retry/fail + interrupted-attempt cap (#130) | Implemented |
| [f9-data-export.md](f9-data-export.md) | F9: Data export — ZIP archive CLI + `GET /api/export/` + dashboard button | Implemented |
| [f10-data-deletion.md](f10-data-deletion.md) | F10: Data deletion — soft/hard delete, `DELETE /api/user-data/`, management command | Implemented |
| [f21-concern-flagging.md](f21-concern-flagging.md) | F21: Proactive concern flagging — advisory `flag_concerns` action in the planning phase, surfaced on run detail | Implemented |
| [f22-dilemma-escalation.md](f22-dilemma-escalation.md) | F22: Dilemma escalation — ethics gate `escalate` verdict + human resolution task showing both sides | Implemented |
| [f28-event-bus.md](f28-event-bus.md) | F28: Event-driven trigger bus — forward spec (NOT YET IMPLEMENTED, deferred from original close) | Forward spec |
| [memory-vector-embeddings-design.md](memory-vector-embeddings-design.md) | #169: Goal-relevant memory/knowledge retrieval via Oracle 26ai in-database embeddings (ONNX model from Object Storage, triggers, `VECTOR_DISTANCE`), keyword fallback elsewhere | Implemented |
| [llm-agent-tools-design.md](llm-agent-tools-design.md) | #146: LLM tool use via workflows: engine suspend-on-subflow (`AWAITING_SUBFLOW`, `TaskResult.suspend`), `llm_agent` action, workflow `inputs:` schemas, `define_workflow` | Implemented |
| [run-trace-design.md](run-trace-design.md) | #184: engine step journal (`ProcessEvent` with property diffs, replay) and the step trace page across parent and subflows | Implemented |
| [llm-spend-ledger-design.md](llm-spend-ledger-design.md) | #206: append-only LLM spend ledger (one row per call) for the daily budget; run records get their process tree's full spend | Implemented |
| [openrouter-llm-design.md](openrouter-llm-design.md) | #204/#205: every LLM call through OpenRouter; cost tiers low/medium/high/max via `openrouter/auto`, `get_llm(model, context)` records cost, legacy model names read as tiers | Implemented |
| [replay-debugger-design.md](replay-debugger-design.md) | #170: replay a finished process from its step journal at no LLM cost (`create_replay`, `__replay__` marker, recorded steps served instead of actions), live-step override, `manage.py replay_process`, Replay form on the step trace | Implemented |
| [web-ui-design.md](web-ui-design.md) | #159–#163: web UI frame and voice rules: tokens, light/dark theme with enforced WCAG AA, components, voice layer, copy | Implemented |
| [bug-report-design.md](bug-report-design.md) | #186: "Report a bug" dialog capturing user + technical view, stored as a system *Bug Report* workflow with a human review task; `/bugs/` list | Implemented |
| [postmortem-journal-design.md](postmortem-journal-design.md) | #175: postmortems for failed / timed-out / badly rated goals stored in `MemoryStore`, recalled by `consult_memory` into the selector and child goal; `/journal/` page | Implemented |
| [golden-gym-design.md](golden-gym-design.md) | #171: golden tasks (`zebra-agent/golden/`), LLM-judged `run_golden_gym`, Dream Cycle promotion gate for self-modified workflows (fails closed), *Golden Gym* on-demand runs, `gym_scores`, `/gym/` page | Implemented |
| [outcome-review-design.md](outcome-review-design.md) | #190: outcomes agreed at a feature's start; after deploy Zebra (reading its own source) and Claude review blind, compare, and escalate disagreement as a human task that blocks sign-off | Implemented |
| [claude-code-builder-design.md](claude-code-builder-design.md) | #98 + #172: Claude Code builds in a podman sandbox run by a host builder service (spool directory, capability budgets, escape probe), parked on an external wait the daemon's `BuilderWatcher` completes, published as a draft MR only after a human approves the exact patch | Implemented |
| [podman-single-host-design.md](podman-single-host-design.md) | F117: Single-host rootless Podman deployment (Quadlet web + daemon, GitLab shell runner) — replaces the lost OKE cluster (F108–F111) | Implemented |
| [zebra-commons-design.md](zebra-commons-design.md) | #41: Zebra Commons — small Zebras share learnt workflows (only workflows) over Nostr: instance keypair, content-hashed signed offers, attestations, local weighted web of trust, reputation market (points, LMSR, outcome settlement), private skill sync between one Zebra's devices (home/work; workflows only, never data), judged import through ethics gate + gym + `sharing` trust domain | Draft (concept) |

The concrete feature backlog is tracked as [GitLab issues](https://gitlab.com/gidley/zebra/-/issues).

## Conventions

- Requirements live in `docs/requirements.md`
- Design specs live here in `specs/`
- Update this index when adding new files

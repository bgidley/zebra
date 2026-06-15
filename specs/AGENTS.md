# Specs Directory Index

This directory contains requirements and design specifications for Zebra.

## Documents

| File | Purpose | Status |
|------|---------|--------|
| [zebra-as-is.md](zebra-as-is.md) | Snapshot of the current implementation: architectural layers, per-package capabilities, strengths, weaknesses, gaps vs. requirements | Current |
| [zebra-to-be.md](zebra-to-be.md) | High-level technical design for the target system: subsystems, interfaces, migration path, risks | Draft |
| [distributed-data-model.md](distributed-data-model.md) | Design for local-first multi-user data sync (Phase 3) | Draft |
| [testing-strategy.md](testing-strategy.md) | Testing philosophy: E2E black-box through the web UX as primary layer, narrow units only for stable contracts | Draft |
| [f2-kill-switch.md](f2-kill-switch.md) | F2: Kill switch — `SystemStateModel`, daemon halted flag, web endpoint, management command | Implemented |
| [f3-observability.md](f3-observability.md) | F3: Observability — structlog JSON logging, Prometheus `/metrics`, `/health` endpoint, partial correlation ID | Implemented |
| [f4-f5-identity-auth.md](f4-f5-identity-auth.md) | F4+F5: Single-user identity setup flow + passkey (WebAuthn) web authentication | Implemented |
| [f6-user-id-namespacing.md](f6-user-id-namespacing.md) | F6: user_id columns on all Django store tables, `CurrentUserMiddleware` ContextVar propagation | Implemented |
| [f7-credential-store.md](f7-credential-store.md) | F7: OS keychain credential store — `CredentialStore` ABC, keyring + file backends, CLI commands | Implemented |
| [f8-crash-recovery.md](f8-crash-recovery.md) | F8: Crash recovery contract — write-ahead guarantees, daemon startup `resume_all_processes`, 11-test matrix | Implemented |
| [f9-data-export.md](f9-data-export.md) | F9: Data export — ZIP archive CLI + `GET /api/export/` + dashboard button | Implemented |
| [f10-data-deletion.md](f10-data-deletion.md) | F10: Data deletion — soft/hard delete, `DELETE /api/user-data/`, management command | Implemented |
| [f21-concern-flagging.md](f21-concern-flagging.md) | F21: Proactive concern flagging — advisory `flag_concerns` action in the planning phase, surfaced on run detail | Implemented |
| [f22-dilemma-escalation.md](f22-dilemma-escalation.md) | F22: Dilemma escalation — ethics gate `escalate` verdict + human resolution task showing both sides | Implemented |
| [f28-event-bus.md](f28-event-bus.md) | F28: Event-driven trigger bus — forward spec (NOT YET IMPLEMENTED, deferred from original close) | Forward spec |

The concrete feature backlog is tracked as [GitLab issues](https://gitlab.com/gidley/zebra/-/issues).

## Conventions

- Requirements live in `docs/requirements.md`
- Design specs live here in `specs/`
- Update this index when adding new files

# Specs Directory Index

This directory contains requirements and design specifications for Zebra.

## Documents

| File | Purpose | Status |
|------|---------|--------|
| [zebra-as-is.md](zebra-as-is.md) | Snapshot of the current implementation: architectural layers, per-package capabilities, strengths, weaknesses, gaps vs. requirements | Current |
| [zebra-to-be.md](zebra-to-be.md) | High-level technical design for the target system: subsystems, interfaces, migration path, risks | Draft |
| [distributed-data-model.md](distributed-data-model.md) | Design for local-first multi-user data sync (Phase 3) | Draft |
| [testing-strategy.md](testing-strategy.md) | Testing philosophy: E2E black-box through the web UX as primary layer, narrow units only for stable contracts | Draft |
| [f10-data-deletion.md](f10-data-deletion.md) | Data deletion design: soft/hard delete modes, API endpoint, management command (F10 / REQ-DATA-005) | Implemented |

The concrete feature backlog is tracked as [GitLab issues](https://gitlab.com/gidley/zebra/-/issues).

## Conventions

- Requirements live in `docs/requirements.md`
- Design specs live here in `specs/`
- Update this index when adding new files

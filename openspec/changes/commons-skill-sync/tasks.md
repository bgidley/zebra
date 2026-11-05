> Branch: `f236/commons-sync-logic`. Reference `Refs #236` in commits.

## 1. Transport and events

- [x] 1.1 `zebra_agent/commons/client.py`: `CommonsClient` ABC, `Filter`, `InMemoryRelay`, `InMemoryCommonsClient`, SKILL hard filter
- [x] 1.2 `zebra_agent/commons/skill.py`: recipients, `build_skill_events`, `verify_skill`
- [x] 1.3 Tests: recipients by sphere, verify reasons (addressee, signature, chain, revoked, hash, foreign, sphere)

## 2. Library and curator

- [x] 2.1 Lineage-aware current-file lookup; `approve_share`, `set_fork_of`, `resolve_fork`; adopt `replace=` / `fork_of=`; sync saves journaled
- [x] 2.2 Curator `SUPERSEDED_COPY` by lineage, forks skipped
- [x] 2.3 Tests

## 3. Sync logic and gates

- [x] 3.1 `zebra_agent/commons/sync.py`: directions, `merge_decision`, share journal and status, candidates, `SyncService` (after_run, after_dream, start_share, receive_pending, apply_received)
- [x] 3.2 `commons_confidentiality_scan`, `commons_sensitivity_check` (fail closed)
- [x] 3.3 Sync actions: prepare, route, record, send, receive verify, receive adopt, fork resolve
- [x] 3.4 System workflows `skill_share.yaml`, `skill_receive.yaml`; dream-cycle hook
- [x] 3.5 Unit tests of the scans and actions

## 4. E2E and genealogy

- [x] 4.1 Two-device E2E (home + observed work): the seven #236 scenarios
- [x] 4.2 Genealogy share status and forks; web template text
- [x] 4.3 Docs: `specs/zebra-commons-design.md`, `specs/zebra-as-is.md`, AGENTS.md files
- [x] 4.4 Review fix: leak-guard taint fails closed — `save_check` kept in the journal, a crashed
  save-time check journaled as `error`, `kept` / `error` on any ancestor taints, `send` re-checks;
  E2E tests for a kept save, a kept ancestor, a merged writer + save record and an `error`

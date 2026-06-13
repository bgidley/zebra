# Tasks — emergency-override (branch f16/emergency-override, GitLab #16)

## 1. Store (zebra-agent)

- [x] 1.1 Add `pause_all(user_id, reason, changed_by) -> list[str]` to `TrustStore` ABC
      (`storage/interfaces.py`) and implement in `InMemoryTrustStore` (`storage/trust.py`):
      revert every non-SUPERVISED registered domain via `set_trust_level`, reason
      prefixed "Emergency override:", return reverted domains
- [x] 1.2 InMemory tests in `zebra-agent/tests/test_trust_store.py`: reverts elevated
      domains + audit per domain with changed_by, idempotent on all-supervised, scoped
      to the user

## 2. Django store (zebra-agent-web)

- [x] 2.1 Implement `pause_all` on `DjangoTrustStore` (one `transaction.atomic()` over
      `_set_level_sync`); mirror tests in `tests/unit/test_django_trust_store.py`

## 3. API + Web UI (zebra-agent-web)

- [x] 3.1 `POST /api/trust/pause-all/` view + route (auth, own-user, returns reverted
      domains); API tests (auth required, reverts + audit changed_by)
- [x] 3.2 `/trust/pause-all/` web view + emergency button on `templates/pages/trust.html`;
      UI test that POST reverts and redirects

## 4. E2E (issue #16 criterion)

- [x] 4.1 zebra-tasks gate e2e: AUTONOMOUS `code` workflow gate proceeds → `pause_all`
      → next `trust_gate` routes to approval (previously-auto workflow now needs approval)

## 5. Docs + verification

- [x] 5.1 `specs/zebra-as-is.md` (F16 implemented), `zebra-agent-web/AGENTS.md` URL table
- [x] 5.2 Full local suite (baseline 1590) + `ruff check --fix` + `ruff format`

## 6. Feedback, commit, CI

- [x] 6.1 `bash scripts/zebra-feedback.sh 16 "Emergency override — revert all to SUPERVISED" "<changes>"`
- [x] 6.2 Commit `Closes #16`, push, pipeline green (pipeline #2598835724)
- [ ] 6.3 Archive change (sync spec), GitHub PR, merge, verify deploy + smoke, issue #16 closed

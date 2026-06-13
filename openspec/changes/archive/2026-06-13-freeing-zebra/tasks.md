# Tasks — freeing-zebra (branch f17/freeing-zebra, GitLab #17)

## 1. Store lifecycle (zebra-agent)

- [x] 1.1 `FreeingStatus` dataclass + `FREEING_*` state constants in `storage/trust.py`;
      add `initiate_freeing`, `confirm_freeing`, `cancel_freeing`, `is_freed`,
      `freed_at`, `get_freeing_status` to `TrustStore` ABC (`storage/interfaces.py`);
      amend `pause_all` to no-op when freed
- [x] 1.2 Implement in `InMemoryTrustStore` (cooling-off constructor arg, default 24h):
      initiate requires all-AUTONOMOUS, confirm requires cooling-off elapsed + pending,
      cancel pending-only, freed permanent
- [x] 1.3 InMemory tests in `zebra-agent/tests/test_trust_store.py`: initiate blocked
      unless all-AUTONOMOUS, confirm blocked during cooling-off, confirm frees after
      cooling-off, cancel pending, cancel-after-freed fails, pause_all no-op when freed

## 2. Django store (zebra-agent-web)

- [x] 2.1 `TrustFreedModel` + migration 0021 (ruff after makemigrations); implement the
      six methods + pause_all no-op on `DjangoTrustStore` (cooling-off constructor arg)
- [x] 2.2 Mirror tests in `tests/unit/test_django_trust_store.py`

## 3. Gate short-circuit (zebra-tasks)

- [x] 3.1 `trust_gate` proceeds with `level="FREED"` when `is_freed(user_id)` (before
      level read/assessment), guarded with getattr; unit + e2e tests (freed gate proceeds
      regardless of stored level)

## 4. API + Web UI + disable flag (zebra-agent-web)

- [x] 4.1 `ZEBRA_DISABLE_FREEING` setting; `GET /api/trust/freeing/`,
      `POST /api/trust/freeing/{initiate,confirm,cancel}/` (auth, own-user, 403 when
      disabled) + routes; API tests
- [x] 4.2 Freeing section on `templates/pages/trust.html` (eligibility, multi-step
      initiate, cooling-off countdown, confirm/cancel, freed banner) + form-POST web
      views + routes; UI test
- [x] 4.3 E2E (issue #17 criterion): all-AUTONOMOUS → initiate → (cooling-off=0) confirm
      via API → trust_gate proceeds (bypassed) → cancel-after-freed fails (cannot revert)

## 5. Docs + verification

- [x] 5.1 `specs/zebra-as-is.md` (F17 implemented — phase 2 complete),
      `zebra-agent-web/AGENTS.md` URL table
- [x] 5.2 Full local suite (baseline 1600) + `ruff check --fix` + `ruff format`

## 6. Feedback, commit, CI

- [x] 6.1 `bash scripts/zebra-feedback.sh 17 "Freeing Zebra — full autonomous promotion" "<changes>"`
- [x] 6.2 Commit `Closes #17`, push, pipeline green (pipeline #2599329847)
- [ ] 6.3 Archive change (sync spec), GitHub PR, merge, verify deploy + smoke, issue #17 closed

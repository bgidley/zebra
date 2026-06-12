# Tasks — trust-promotion (branch f15/trust-promotion, GitLab #15)

## 1. Suggestion store API (zebra-agent)

- [x] 1.1 `TrustSuggestion` dataclass in `storage/trust.py`; +3 ABC methods on
      `TrustStore` (`add_suggestion`, `list_suggestions`, `resolve_suggestion`) in
      `storage/interfaces.py`; implement in `InMemoryTrustStore`; export in
      `storage/__init__.py`
- [x] 1.2 InMemory tests in `zebra-agent/tests/test_trust_store.py`: add/list/filter,
      approve changes level + audit with resolver, reject leaves level, double-resolve
      and unknown domain/level rejected

## 2. Django backend (zebra-agent-web)

- [x] 2.1 `TrustSuggestionModel` + migration 0020 (ruff immediately after
      makemigrations); implement the 3 methods on `DjangoTrustStore` (approve in one
      `transaction.atomic()`)
- [x] 2.2 Mirror tests in `tests/unit/test_django_trust_store.py`

## 3. Agent action (zebra-tasks)

- [x] 3.1 `ProposeTrustPromotionAction` in `zebra_tasks/agent/propose_trust_promotion.py`
      + entry point + `uv sync --all-packages`
- [x] 3.2 Tests in `zebra-tasks/tests/test_propose_trust_promotion.py`: creates pending
      suggestion, store absent → `submitted: False`, template resolution, invalid
      domain/level → fail

## 4. API endpoints (zebra-agent-web)

- [x] 4.1 Views + routes: `GET /api/trust/`, `POST /api/trust/<domain>/`,
      `GET /api/trust/changes/`, `GET /api/trust/suggestions/`,
      `POST /api/trust/suggestions/<id>/resolve/` (sync-DRF + async_to_sync pattern,
      own-user scope)
- [x] 4.2 API tests (`transaction=True`): auth required, set-level + audit changed_by,
      invalid level 400, suggestion list/resolve flow

## 5. Web UI (zebra-agent-web)

- [x] 5.1 `/trust/` page (`templates/pages/trust.html`, `trust_page` view) + form-POST
      views `/trust/<domain>/set/` and `/trust/suggestions/<id>/resolve/`; nav item in
      `base.html`; dashboard trust card links to `/trust/`
- [x] 5.2 UI tests: page renders all domains + pending suggestions for authenticated
      user; POST set-level redirects and persists

## 6. E2E (issue #15 criterion)

- [x] 6.1 Test: agent action (DjangoTrustStore via extras) submits suggestion → pending
      via `GET /api/trust/suggestions/?status=pending` → user approves via resolve
      endpoint → level changed, `changed_by` = human, suggestion `approved`

## 7. Docs and verification

- [x] 7.1 Update `specs/zebra-as-is.md` (F15 implemented), `zebra-tasks/AGENTS.md`,
      `zebra-agent-web/AGENTS.md` URL table
- [x] 7.2 Full local suite (baseline 1560) + `ruff check --fix` + `ruff format`

## 8. Feedback, commit, CI

- [x] 8.1 `bash scripts/zebra-feedback.sh 15 "Human-only trust promotion/demotion" "<changes>"`
- [ ] 8.2 Commit `Closes #15`, push, pipeline green
- [ ] 8.3 Archive change (sync spec), GitHub PR, merge, verify deploy + smoke, issue
      #15 closed

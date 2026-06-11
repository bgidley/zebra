# Tasks — trust-level-model (branch f12/trust-level-model, GitLab #12)

## 1. Core models and store interface (zebra-agent)

- [x] 1.1 Create `zebra-agent/zebra_agent/storage/trust.py`: `TrustLevel` StrEnum
      (SUPERVISED / SEMI_AUTONOMOUS / AUTONOMOUS), `TrustChangeRecord` Pydantic model,
      `DOMAIN_REGISTRY` seeded with the eight canonical domains, `register_domain()` /
      `list_domains()` helpers
- [x] 1.2 Add `TrustStore` ABC to `zebra-agent/zebra_agent/storage/interfaces.py`:
      `get_trust_level`, `set_trust_level` (validates domain, returns
      `TrustChangeRecord`), `get_all_trust_levels`, `list_trust_changes`
- [x] 1.3 Implement `InMemoryTrustStore` in `trust.py` (defaults to SUPERVISED on
      unknown pairs, append-only change list)
- [x] 1.4 Unit tests in `zebra-agent/tests/test_trust_store.py` covering every spec
      scenario: default read, set/read-back, user scoping, unknown-domain rejection,
      get_all merge over registry, custom domain registration, audit record content
      and ordering

## 2. Django-backed store (zebra-agent-web)

- [x] 2.1 Add `TrustLevelModel` (unique `(user_id, domain)`) and `TrustChangeModel` to
      `zebra-agent-web/zebra_agent_web/api/models.py`; run `makemigrations` then
      immediately `ruff check --fix . && ruff format .`
- [x] 2.2 Implement `DjangoTrustStore` in `zebra-agent-web/zebra_agent_web/trust_store.py`
      following the existing `sync_to_async` store pattern; level upsert + audit row in
      one transaction
- [x] 2.3 Unit tests in `zebra-agent-web/tests/unit/test_trust_store.py` (django_db),
      mirroring the in-memory test cases

## 3. Engine wiring and dashboard

- [x] 3.1 Inject `engine.extras["__trust_store__"] = DjangoTrustStore()` in
      `zebra-agent-web/zebra_agent_web/api/agent_engine.py` next to the existing
      budget/ethics injections
- [x] 3.2 Add trust-by-domain data to the `dashboard` view (`web_views.py`) using
      `request.user.pk` and `get_all_trust_levels`
- [x] 3.3 Add a read-only "Trust by domain" card to `templates/pages/dashboard.html`
- [x] 3.4 Tests: extras injection test + dashboard view test asserting all domains
      rendered with correct levels (use `transaction=True` for async client fixtures)

## 4. Docs and verification

- [x] 4.1 Update `specs/zebra-as-is.md`: gap item 4 and the F12–F17 status table
      (trust levels: implemented; gates still pending F13)
- [x] 4.2 Run full local suite:
      `uv run pytest --ignore=zebra-agent-web/tests/e2e_live --ignore=zebra-agent-web/tests/e2e -q`
- [x] 4.3 Run `uv run ruff check --fix . && uv run ruff format .`

## 5. Feedback, commit, CI

- [x] 5.1 Run Zebra feedback: `bash scripts/zebra-feedback.sh 12 "Trust level data model" "<changes>"`
- [x] 5.2 Commit (`feat: add per-domain trust level data model` … `Closes #12`), push
      `f12/trust-level-model`, verify GitLab pipeline green (pipeline #156)
- [ ] 5.3 Open GitHub PR, merge to master per CLAUDE.md workflow, verify deploy + smoke
      stages pass, confirm issue #12 closed

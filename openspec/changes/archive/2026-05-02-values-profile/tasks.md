## 1. Branch setup

- [ ] 1.1 Create branch `f18/values-profile` off `master` and push to GitLab to trigger an empty-pipeline baseline

## 2. ProfileStore interface

- [x] 2.1 Add `ProfileStore` ABC to `zebra-agent/zebra_agent/storage/interfaces.py` with `get_current(user_id)`, `get_version(version_id)`, `save_version(user_id, version_data)`
- [x] 2.2 Implement `InMemoryProfileStore` in `zebra-agent/zebra_agent/storage/profile.py`
- [x] 2.3 Write unit tests for `InMemoryProfileStore` covering round-trip save/get, monotonic version numbers, and isolation by `user_id`
- [x] 2.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 3. Django models and migrations

- [x] 3.1 Add `ValuesProfile`, `ValuesProfileVersion`, `Tag` models to `zebra-agent-web/zebra_agent_web/api/models.py` (with `user_id` indexed and `Tag.(field, slug)` unique)
- [x] 3.2 Generate the Django migration via `python manage.py makemigrations api` and inspect it for correctness
- [x] 3.3 Write model-level tests in `zebra-agent-web/tests/test_values_profile_models.py` covering creation, version monotonicity, FK constraints, and `(field, slug)` uniqueness
- [x] 3.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 4. DjangoProfileStore

- [x] 4.1 Implement `DjangoProfileStore` in `zebra-agent-web/zebra_agent_web/profile_store.py` against the `ProfileStore` ABC (placed alongside existing `memory_store.py` / `metrics_store.py` rather than under `api/`)
- [x] 4.2 Inject `engine.extras["__profile_store__"]` in `AgentLoop.__init__` (new `profile` param) and the web engine construction path (`api/agent_engine.py`)
- [x] 4.3 Write integration tests against the test DB confirming `DjangoProfileStore` satisfies the same contract as `InMemoryProfileStore` (uses `transaction=True` per project rules for async + sync_to_async tests)
- [x] 4.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 5. Task actions

- [x] 5.1 Implement `LoadValuesProfileAction` in `zebra-tasks/zebra_tasks/agent/load_values_profile.py` (reads `ProfileStore`, writes `existing_profile.*` into process properties, outputs `{found, mode}`)
- [x] 5.2 Implement `ExtractValuesTagsAction` in `zebra-tasks/zebra_tasks/agent/extract_values_tags.py` (LLM call; passes approved-tag set per field; returns `{<field>: {approved_tags, candidate_tags}}`; returns success with empty sets on any failure; caps candidates at 5 per field; drops hallucinated approved tags)
- [x] 5.3 Implement `SaveValuesProfileAction` in `zebra-tasks/zebra_tasks/agent/save_values_profile.py` (writes new `Version` via `ProfileStore.save_version`, then `record_confirmed_tags` upserts `Tag` rows + increments `usage_count`)
- [x] 5.4 Register all three actions as `zebra.tasks` entry points in `zebra-tasks/pyproject.toml`
- [x] 5.5 Run `uv sync --all-packages` to refresh entry points
- [x] 5.6 Write unit tests for each action with mocked stores and a mocked LLM in `zebra-tasks/tests/test_values_profile_actions.py` (covering happy path, LLM failure → empty tags, candidate→`usage_count` upsert, capping, hallucination drop)
- [x] 5.7 Run `uv run ruff check --fix . && uv run ruff format .`

Note: extended `ProfileStore` (and both implementations) with `get_approved_tags(field)` and `record_confirmed_tags(field_to_tags)` so the actions don't need direct ORM access (per the storage-abstraction rule in CLAUDE.md).

## 6. Wizard workflow YAML

- [x] 6.1 Create `zebra-agent/workflows/values_profile_wizard.yaml` with eight steps (load, four free-form forms, extract, review, save) and the routing chain
- [x] 6.2 Define each human-task step's JSON schema with `default: "{{existing_profile.<field>_text}}"` for pre-population in edit mode (LoadValuesProfileAction also sets `existing_profile.mode = capture|edit`)
- [x] 6.3 Write an end-to-end workflow test that runs the wizard with an in-memory engine + `InMemoryProfileStore`, in both capture and edit modes
- [x] 6.4 Run `uv run ruff check --fix . && uv run ruff format .`

Notes during 6:
- The engine's `resolve_template` only supports `{{task_id.output}}` (whole output, stringified) — it does NOT chain `.output.<key>`. Workaround: forms reference each other via `{{__task_output_<task_def_id>.<key>}}` (the underlying process property the engine writes), which DOES support nested dict navigation.
- For lists, even that path stringifies the value. So `save_values_profile` got a new `from_task_id` property: when set, the action reads the upstream human task's output dict directly via `context.get_task_output(...)`, bypassing template stringification.

## 7. System-workflow allowlist

- [x] 7.1 Add `"Values Profile Wizard"` to `_is_system_workflow` in `zebra-agent/zebra_agent/loop.py`
- [x] 7.2 Add a unit test confirming the wizard is excluded

## 8. Web entrypoint

- [x] 8.1 Implement `values_profile_wizard` async view in `zebra-agent-web/zebra_agent_web/api/web_views.py` — auth-required (anonymous → setup redirect), checks `ProfileStore.get_current` for an existing profile, creates + starts a wizard process with `user_id` (and `existing_profile_version_id` if found), redirects to the first pending human task
- [x] 8.2 Wire `path("profile/values/", web_views.values_profile_wizard, name="values_profile_wizard")` in `zebra-agent-web/zebra_agent_web/urls.py`
- [x] 8.3 Three integration tests: anonymous redirect, capture mode (no existing profile), edit mode (`existing_profile_version_id` stamped + `existing_profile.mode == "edit"`)
- [x] 8.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 9. Taxonomy bootstrap

- [x] 9.1 Implement `zebra-agent-web/zebra_agent_web/api/management/commands/bootstrap_values_taxonomy.py` (calls LLM via `zebra_tasks.llm.get_provider`, resolving model alias via `resolve_model_name`; validates per-field shape; writes YAML fixture; refuses to overwrite without `--force`)
- [x] 9.2 Ran the command locally and hand-reviewed the produced YAML (39 tags across 4 fields)
- [x] 9.3 Committed the reviewed fixture at `zebra-agent-web/fixtures/values_taxonomy_seed.yaml`
- [x] 9.4 Added Django data migration `0013_seed_values_taxonomy` that loads the fixture into `ValuesTagModel` rows with `status="seeded"`. Idempotent (`get_or_create`); reverse migration removes only seeded rows matching the fixture (candidate/promoted preserved); falls back to no-op if fixture is absent.
- [x] 9.5 Write a unit test for the command's idempotency behaviour (no-overwrite by default; overwrite with `--force`; validation rejects malformed payload)
- [x] 9.6 Run `uv run ruff check --fix . && uv run ruff format .`

Notes during 9:
- Initial run failed because the bootstrap passed the friendly model alias (`sonnet`) to the Anthropic API directly. Aliases are resolved at the boundary by callers (web views do this); the bootstrap now uses `resolve_model_name(model)` before constructing the provider.
- Default fixture path was off by one `.parent` walk (landed in inner `zebra_agent_web/fixtures/` instead of outer `zebra-agent-web/fixtures/`). Fixed.
- Three model tests collided with seeded slugs (`honesty`, `family`); they now use deliberately-non-colliding `test-*` slugs.

## 10. Documentation

- [x] 10.1 Add a "Values profile (F18 / REQ-ETH-002)" section to `specs/zebra-as-is.md` (under § 5 Agent Library, after Ethics gates) covering data model, hybrid taxonomy with status lifecycle, wizard workflow, bootstrap command, web entrypoint, and the explicit non-goal of gate consumption (deferred to REQ-ETH-003). Also struck through two now-resolved weaknesses in § 5.
- [x] 10.2 No new sub-file needed (the section is short enough to live inline in zebra-as-is.md), so `specs/AGENTS.md` index untouched.
- [x] 10.3 Updated `zebra-agent/CLAUDE.md` storage section to list `ProfileStore` (interface), `InMemoryProfileStore` (CLI default), and `DjangoProfileStore` (web).

## 11. CI and merge — awaits maintainer

- [x] 11.1 Local test suite ran: 1070 zebra-tasks tests + 140 zebra-agent-web unit tests + zebra-agent + zebra-py all green. The 1 failed e2e test (`test_budget_exhaustion.py`) and the e2e-live errors are pre-existing — they need Oracle + ANTHROPIC_API_KEY wired into the local env.
- [x] 11.2 Ruff lint + format clean (run after each group's commit).
- [ ] 11.3 Push `f18/values-profile` to GitLab; verify the pipeline progresses `lint → unit → e2e` to green via `glab ci list --repo gidley/zebra --per-page 1` — **awaits user (shared state)**
- [ ] 11.4 Push the branch to GitHub and open a PR titled `F18: Values profile`, body referencing GitLab issue #18 and the pipeline URL — **awaits user**
- [ ] 11.5 After review, merge to `master` with `git merge --no-ff f18/values-profile -m "Merge f18/values-profile — Closes #18"` — **awaits user**
- [ ] 11.6 Push `master` to GitLab (triggers deploy) and to GitHub (closes the PR); delete the feature branch from both remotes — **awaits user**
- [ ] 11.7 Verify the `deploy` stage of the master pipeline succeeds — **awaits user**

## 12. Follow-up

- [ ] 12.1 Open a GitLab issue for "Values taxonomy promotion mechanism" (label `phase::3-values-ethics`) and link it from issue #18 as the deferred work

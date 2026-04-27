## 1. Branch setup

- [ ] 1.1 Create branch `f18/values-profile` off `master` and push to GitLab to trigger an empty-pipeline baseline

## 2. ProfileStore interface

- [ ] 2.1 Add `ProfileStore` ABC to `zebra-agent/zebra_agent/storage/interfaces.py` with `get_current(user_id)`, `get_version(version_id)`, `save_version(user_id, version_data)`
- [ ] 2.2 Implement `InMemoryProfileStore` in `zebra-agent/zebra_agent/storage/profile.py`
- [ ] 2.3 Write unit tests for `InMemoryProfileStore` covering round-trip save/get, monotonic version numbers, and isolation by `user_id`
- [ ] 2.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 3. Django models and migrations

- [ ] 3.1 Add `ValuesProfile`, `ValuesProfileVersion`, `Tag` models to `zebra-agent-web/zebra_agent_web/api/models.py` (with `user_id` indexed and `Tag.(field, slug)` unique)
- [ ] 3.2 Generate the Django migration via `python manage.py makemigrations api` and inspect it for correctness
- [ ] 3.3 Write model-level tests in `zebra-agent-web/tests/test_values_profile_models.py` covering creation, version monotonicity, FK constraints, and `(field, slug)` uniqueness
- [ ] 3.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 4. DjangoProfileStore

- [ ] 4.1 Implement `DjangoProfileStore` in `zebra-agent-web/zebra_agent_web/api/stores.py` against the `ProfileStore` ABC
- [ ] 4.2 Inject `engine.extras["__profile_store__"]` in `AgentLoop.__init__` (in-memory backend for CLI) and the web/daemon engine construction path
- [ ] 4.3 Write integration tests against a real DB confirming `DjangoProfileStore` satisfies the same contract as `InMemoryProfileStore`
- [ ] 4.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 5. Task actions

- [ ] 5.1 Implement `LoadValuesProfileAction` in `zebra-tasks/zebra_tasks/agent/load_values_profile.py` (reads `ProfileStore`, writes `existing_profile.*` into process properties, outputs `{found: bool}`)
- [ ] 5.2 Implement `ExtractValuesTagsAction` in `zebra-tasks/zebra_tasks/agent/extract_values_tags.py` (LLM call; passes approved-tag set per field; returns `{<field>: {approved_tags, candidate_tags}}`; returns success with empty sets on any failure)
- [ ] 5.3 Implement `SaveValuesProfileAction` in `zebra-tasks/zebra_tasks/agent/save_values_profile.py` (writes new `Version`, bumps `current_version`, upserts `Tag` rows + increments `usage_count`, all in one transaction)
- [ ] 5.4 Register all three actions as `zebra.tasks` entry points in `zebra-tasks/pyproject.toml`
- [ ] 5.5 Run `uv sync --all-packages` to refresh entry points
- [ ] 5.6 Write unit tests for each action with mocked stores and a mocked LLM in `zebra-tasks/tests/test_values_profile_actions.py` (covering happy path, LLM failure → empty tags, candidate→`usage_count` upsert)
- [ ] 5.7 Run `uv run ruff check --fix . && uv run ruff format .`

## 6. Wizard workflow YAML

- [ ] 6.1 Create `zebra-agent/workflows/values_profile_wizard.yaml` with eight steps (load, four free-form forms, extract, review, save) and the routing chain
- [ ] 6.2 Define each human-task step's JSON schema, using `default: "{{existing_profile.<field>_text}}"` for pre-population in edit mode
- [ ] 6.3 Write an end-to-end workflow test that runs the wizard with an in-memory engine + `InMemoryProfileStore`, in both capture mode and edit mode
- [ ] 6.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 7. System-workflow allowlist

- [ ] 7.1 Add `"Values Profile Wizard"` to `_is_system_workflow` in `zebra-agent/zebra_agent/loop.py`
- [ ] 7.2 Add a unit test confirming the wizard is filtered out of the LLM-selectable workflow list

## 8. Web entrypoint

- [ ] 8.1 Implement `ValuesProfileWizardStartView` in `zebra-agent-web/zebra_agent_web/api/views.py` (auth-required; checks for existing profile; starts a wizard process; redirects to the first pending task)
- [ ] 8.2 Wire `path("profile/values/", ValuesProfileWizardStartView.as_view(), name="values_profile_wizard")` in `zebra-agent-web/zebra_agent_web/urls.py`
- [ ] 8.3 Write Django integration tests covering anonymous (auth-required behaviour), user with no profile (capture mode), and user with existing profile (edit mode with `existing_profile_version_id` set)
- [ ] 8.4 Run `uv run ruff check --fix . && uv run ruff format .`

## 9. Taxonomy bootstrap

- [ ] 9.1 Implement `zebra-agent-web/zebra_agent_web/api/management/commands/bootstrap_values_taxonomy.py` (calls LLM; writes YAML fixture; refuses to overwrite existing fixture without `--force`)
- [ ] 9.2 Run the command locally and hand-review the produced YAML
- [ ] 9.3 Commit the reviewed fixture at `zebra-agent-web/fixtures/values_taxonomy_seed.yaml`
- [ ] 9.4 Add a Django data migration that loads the fixture into `Tag` rows with `status="seeded"`
- [ ] 9.5 Write a unit test for the command's idempotency behaviour (no-overwrite by default; overwrite with `--force`)
- [ ] 9.6 Run `uv run ruff check --fix . && uv run ruff format .`

## 10. Documentation

- [ ] 10.1 Add a "Values Profile" section to `specs/zebra-as-is.md` covering data model, wizard workflow, `ProfileStore`, and taxonomy bootstrap
- [ ] 10.2 Update `specs/AGENTS.md` index if a new sub-file is created
- [ ] 10.3 Update `zebra-agent/AGENTS.md` storage section to list `ProfileStore` alongside `MemoryStore` and `MetricsStore`

## 11. CI and merge

- [ ] 11.1 Run the full local test suite: `uv run pytest`
- [ ] 11.2 Run `uv run ruff check --fix . && uv run ruff format .` one final time
- [ ] 11.3 Push `f18/values-profile` to GitLab; verify the pipeline progresses `lint → unit → e2e` to green via `glab ci list --repo gidley/zebra --per-page 1`
- [ ] 11.4 Push the branch to GitHub and open a PR titled `F18: Values profile`, body referencing GitLab issue #18 and the pipeline URL
- [ ] 11.5 After review, merge to `master` with `git merge --no-ff f18/values-profile -m "Merge f18/values-profile — Closes #18"`
- [ ] 11.6 Push `master` to GitLab (triggers deploy) and to GitHub (closes the PR); delete the feature branch from both remotes
- [ ] 11.7 Verify the `deploy` stage of the master pipeline succeeds

## 12. Follow-up

- [ ] 12.1 Open a GitLab issue for "Values taxonomy promotion mechanism" (label `phase::3-values-ethics`) and link it from issue #18 as the deferred work

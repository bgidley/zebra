## 1. Branch setup

- [x] 1.1 Create feature branch: `git checkout -b f31/personal-knowledge-store`

## 2. Core data model and interface (zebra-agent)

- [x] 2.1 Create `zebra-agent/zebra_agent/knowledge.py` with `KnowledgeEntry` dataclass, `KNOWLEDGE_CATEGORIES` constant, and `KnowledgeEntry.create()` factory (validates category, auto-generates UUID/timestamps)
- [x] 2.2 Add `PersonalKnowledgeStore` ABC to `zebra-agent/zebra_agent/storage/interfaces.py` (methods: `initialize`, `close`, `add_entry`, `update_entry`, `delete_entry`, `get_entry`, `get_entries`, `get_context_for_llm`)
- [x] 2.3 Add `InMemoryPersonalKnowledgeStore` to `zebra-agent/zebra_agent/storage/memory.py`
- [x] 2.4 Update `zebra-agent/zebra_agent/loop.py` to accept optional `knowledge: PersonalKnowledgeStore | None` parameter and inject `__knowledge_store__` into `engine.extras`
- [x] 2.5 Write unit tests in `zebra-agent/tests/test_knowledge.py` covering: `KnowledgeEntry.create()` defaults and validation, `InMemoryPersonalKnowledgeStore` add/list/delete/update, `get_context_for_llm` formatting, and graceful handling of `user_id=None`

## 3. consult_knowledge task action (zebra-tasks)

- [x] 3.1 Create `zebra-tasks/zebra_tasks/agent/consult_knowledge.py` with `ConsultKnowledgeAction` — reads `__user_id__` from process properties, calls `knowledge_store.get_context_for_llm(user_id)`, degrades gracefully when store/user_id absent
- [x] 3.2 Register `consult_knowledge` entry-point in `zebra-tasks/pyproject.toml` under `[project.entry-points."zebra.tasks"]`
- [x] 3.3 Run `uv sync --all-packages` to refresh entry points
- [x] 3.4 Write unit tests in `zebra-tasks/tests/test_consult_knowledge.py` covering: happy path with mock store, degradation when store is None, degradation when user_id is None

## 4. Selector integration (zebra-tasks)

- [x] 4.1 Add optional `knowledge_context` input parameter (default `""`) to `WorkflowSelectorAction` in `zebra-tasks/zebra_tasks/agent/selector.py`
- [x] 4.2 Append knowledge context under a `## Personal Knowledge` heading in the selector's LLM user prompt when non-empty
- [x] 4.3 Update selector unit tests to verify knowledge_context appears in prompt when provided and is absent when empty

## 5. Agent main loop YAML (zebra-agent)

- [x] 5.1 Add `consult_knowledge` task step to `zebra-agent/workflows/agent_main_loop.yaml` after `consult_memory`, before `ethics_input_gate`
- [x] 5.2 Add routing `consult_memory → consult_knowledge → ethics_input_gate`
- [x] 5.3 Add `knowledge_context: "{{knowledge_context.knowledge}}"` property to the `select_workflow` task in the YAML

## 6. Django model and store (zebra-agent-web)

- [x] 6.1 Add `KnowledgeEntryModel` to `zebra-agent-web/zebra_agent_web/api/models.py` with all columns per the design (id, user_id, category, key, value, source, confidence, last_verified, created_at, updated_at) and a composite index on `(user_id, category)`
- [x] 6.2 Generate migration: `uv run python manage.py makemigrations` and verify the migration file
- [x] 6.3 Create `zebra-agent-web/zebra_agent_web/knowledge_store.py` with `DjangoPersonalKnowledgeStore` — all ORM calls wrapped in `sync_to_async`, consistent with `DjangoMemoryStore` pattern

## 7. Agent engine injection (zebra-agent-web)

- [x] 7.1 Update `zebra-agent-web/zebra_agent_web/api/agent_engine.py` to initialise `DjangoPersonalKnowledgeStore`, call `await _knowledge.initialize()`, pass it to `AgentLoop(knowledge=_knowledge)`, and inject `engine.extras["__knowledge_store__"] = _knowledge`

## 8. CRUD web UI (zebra-agent-web)

- [x] 8.1 Add knowledge CRUD views to `zebra-agent-web/zebra_agent_web/api/web_views.py`: `knowledge_list`, `knowledge_create`, `knowledge_edit`, `knowledge_delete` (all require `@login_required`, scope to `request.user.id`, return 404 on wrong-user access)
- [x] 8.2 Add URL routes to `zebra-agent-web/zebra_agent_web/urls.py`: `/knowledge/`, `/knowledge/create/`, `/knowledge/<str:entry_id>/edit/`, `/knowledge/<str:entry_id>/delete/`
- [x] 8.3 Create `zebra-agent-web/templates/pages/knowledge_list.html` (list with category filter, add button, edit/delete links per row)
- [x] 8.4 Create `zebra-agent-web/templates/pages/knowledge_form.html` (shared create/edit form with category dropdown, key, value, confidence fields)
- [x] 8.5 Add "Knowledge" nav link to the navigation template

## 9. Lint, format, and CI

- [x] 9.1 Run `uv run ruff check --fix . && uv run ruff format .` and resolve any issues
- [x] 9.2 Run `uv run pytest` and confirm all tests pass
- [x] 9.3 Commit with message: `feat: add personal knowledge store (REQ-MEM-004)\n\nCloses #31`
- [x] 9.4 Push to GitLab (`git push origin f31/personal-knowledge-store`) and verify CI pipeline passes (lint → unit → e2e)
- [x] 9.5 Push branch to GitHub and open PR (`gh pr create --repo bgidley/zebra ...`)

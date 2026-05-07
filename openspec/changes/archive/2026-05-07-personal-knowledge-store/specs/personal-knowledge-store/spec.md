## ADDED Requirements

### Requirement: Knowledge entry data model
The system SHALL define a `KnowledgeEntry` dataclass with fields: `id` (UUID string), `user_id` (int), `category` (one of `preferences`, `facts`, `relationships`, `routines`, `skills`, `history`), `key` (str), `value` (str), `source` (str: `"human"` or `"agent"`), `confidence` (float 0.0–1.0), `last_verified` (datetime), and `created_at` (datetime).

#### Scenario: Entry creation with defaults
- **WHEN** a `KnowledgeEntry` is created via `KnowledgeEntry.create(user_id, category, key, value)`
- **THEN** `id` is a UUID string, `confidence` defaults to 1.0, `source` defaults to `"human"`, and `created_at` / `last_verified` are set to the current UTC time

#### Scenario: Invalid category rejected
- **WHEN** a `KnowledgeEntry` is created with a `category` not in `KNOWLEDGE_CATEGORIES`
- **THEN** a `ValueError` is raised

### Requirement: PersonalKnowledgeStore interface
The system SHALL provide a `PersonalKnowledgeStore` ABC in `zebra_agent.storage.interfaces` with methods: `initialize()`, `close()`, `add_entry(entry)`, `update_entry(entry)`, `delete_entry(entry_id) -> bool`, `get_entry(entry_id) -> KnowledgeEntry | None`, `get_entries(user_id, category=None) -> list[KnowledgeEntry]`, and `get_context_for_llm(user_id, limit=50) -> str`.

#### Scenario: List entries by user
- **WHEN** `get_entries(user_id=42)` is called
- **THEN** only entries belonging to `user_id=42` are returned

#### Scenario: List entries filtered by category
- **WHEN** `get_entries(user_id=42, category="preferences")` is called
- **THEN** only entries with `category="preferences"` and `user_id=42` are returned

#### Scenario: LLM context formatted correctly
- **WHEN** `get_context_for_llm(user_id=42)` is called with two entries
- **THEN** the returned string contains each entry formatted as `[category] key: value` and is non-empty

#### Scenario: Empty store returns empty context
- **WHEN** `get_context_for_llm(user_id=42)` is called and no entries exist
- **THEN** an empty string is returned

### Requirement: In-memory store implementation
The system SHALL provide `InMemoryPersonalKnowledgeStore` implementing `PersonalKnowledgeStore` using an in-memory dict, for use in CLI and tests.

#### Scenario: Add and retrieve entry
- **WHEN** `add_entry(entry)` is called followed by `get_entries(user_id)`
- **THEN** the entry appears in the result list

#### Scenario: Delete entry
- **WHEN** `delete_entry(entry_id)` is called for an existing entry
- **THEN** `True` is returned and the entry no longer appears in `get_entries`

#### Scenario: Delete non-existent entry
- **WHEN** `delete_entry(entry_id)` is called for an unknown ID
- **THEN** `False` is returned

### Requirement: Django ORM store implementation
The system SHALL provide `DjangoPersonalKnowledgeStore` implementing `PersonalKnowledgeStore` backed by `KnowledgeEntryModel`. All ORM calls SHALL be wrapped with `sync_to_async`.

#### Scenario: Persisted entries survive reinitialization
- **WHEN** an entry is added via `DjangoPersonalKnowledgeStore` and a new instance is created
- **THEN** `get_entries(user_id)` on the new instance returns the same entry

### Requirement: consult_knowledge task action
The system SHALL provide a `ConsultKnowledgeAction` registered as the `consult_knowledge` entry-point under `zebra.tasks`. It SHALL read `user_id` from process properties (`__user_id__`) and `goal` from task properties, then call `__knowledge_store__.get_context_for_llm(user_id)` and return `{knowledge: str, has_knowledge: bool}`.

#### Scenario: Knowledge returned when store available
- **WHEN** `consult_knowledge` runs with a populated store and a valid `user_id`
- **THEN** the output contains `knowledge` (non-empty string) and `has_knowledge: true`

#### Scenario: Graceful degradation when no store
- **WHEN** `consult_knowledge` runs and `__knowledge_store__` is not in `context.extras`
- **THEN** the action returns `{knowledge: "", has_knowledge: false}` without raising an exception

#### Scenario: Graceful degradation when user_id is None
- **WHEN** `consult_knowledge` runs and `__user_id__` is `None` in process properties
- **THEN** the action returns `{knowledge: "", has_knowledge: false}` without raising an exception

### Requirement: Agent main loop integration
The system SHALL include a `consult_knowledge` task step in `agent_main_loop.yaml`, positioned after `consult_memory` and before `ethics_input_gate`. The `select_workflow` task SHALL receive a `knowledge_context` property populated from the `consult_knowledge` output.

#### Scenario: Knowledge context flows into selector
- **WHEN** the agent main loop runs and the knowledge store contains entries for the current user
- **THEN** `select_workflow` receives a non-empty `knowledge_context` string

#### Scenario: Loop proceeds without knowledge store
- **WHEN** the agent main loop runs and no `__knowledge_store__` is injected
- **THEN** the loop completes normally with `knowledge_context` as an empty string

### Requirement: WorkflowSelectorAction accepts knowledge_context
The system SHALL extend `WorkflowSelectorAction` with an optional `knowledge_context` input parameter (default `""`). When non-empty, it SHALL be appended to the planning prompt under a "Personal Knowledge" heading.

#### Scenario: Knowledge included in prompt when provided
- **WHEN** `workflow_selector` is called with a non-empty `knowledge_context`
- **THEN** the LLM user message includes the knowledge context

#### Scenario: No change when knowledge_context is empty
- **WHEN** `workflow_selector` is called with `knowledge_context=""`
- **THEN** the LLM prompt is identical to the pre-knowledge baseline

### Requirement: CRUD web UI for knowledge entries
The system SHALL provide web pages at `/knowledge/` for listing, creating, editing, and deleting knowledge entries. All views SHALL require authentication and scope entries to `request.user.id`.

#### Scenario: List page shows all user entries
- **WHEN** an authenticated user visits `/knowledge/`
- **THEN** all their knowledge entries are displayed, grouped or filterable by category

#### Scenario: Create entry via web form
- **WHEN** an authenticated user submits the create form with valid category, key, and value
- **THEN** a new `KnowledgeEntryModel` row is created and the user is redirected to the list page

#### Scenario: Edit entry via web form
- **WHEN** an authenticated user submits the edit form for an existing entry
- **THEN** the entry's `key`, `value`, `confidence`, and `last_verified` are updated

#### Scenario: Delete entry
- **WHEN** an authenticated user POSTs to `/knowledge/<id>/delete/`
- **THEN** the entry is hard-deleted and the user is redirected to the list page

#### Scenario: User cannot access another user's entries
- **WHEN** an authenticated user attempts to edit or delete an entry belonging to a different user
- **THEN** the system returns HTTP 404

### Requirement: store injected into engine extras
The system SHALL inject `DjangoPersonalKnowledgeStore` into `engine.extras["__knowledge_store__"]` during agent engine initialisation, and `AgentLoop.__init__` SHALL accept an optional `knowledge: PersonalKnowledgeStore | None` parameter and inject it into `engine.extras`.

#### Scenario: Knowledge store available to task actions
- **WHEN** the web app is running and a goal is processed
- **THEN** `context.extras.get("__knowledge_store__")` returns a `DjangoPersonalKnowledgeStore` instance inside any task action

## MODIFIED Requirements

### Requirement: Knowledge entry data model
The system SHALL define a `KnowledgeEntry` dataclass with fields: `id` (UUID string), `user_id` (int), `category` (one of `preferences`, `facts`, `relationships`, `routines`, `skills`, `history`), `key` (str), `value` (str), `source` (str: `"human"` or `"agent"`), `confidence` (float 0.0–1.0), `last_verified` (datetime), `created_at` (datetime), `time_sensitive` (bool, default `False`), and `deleted_at` (datetime | None, default `None`).

#### Scenario: Entry creation with defaults
- **WHEN** a `KnowledgeEntry` is created via `KnowledgeEntry.create(user_id, category, key, value)`
- **THEN** `id` is a UUID string, `confidence` defaults to 1.0, `source` defaults to `"human"`, `time_sensitive` defaults to `False`, `deleted_at` defaults to `None`, and `created_at` / `last_verified` are set to the current UTC time

#### Scenario: Invalid category rejected
- **WHEN** a `KnowledgeEntry` is created with a `category` not in `KNOWLEDGE_CATEGORIES`
- **THEN** a `ValueError` is raised

#### Scenario: Time-sensitive entry can be created
- **WHEN** `KnowledgeEntry.create(user_id, category, key, value, time_sensitive=True)` is called
- **THEN** the resulting entry has `time_sensitive=True`

### Requirement: PersonalKnowledgeStore interface
The system SHALL provide a `PersonalKnowledgeStore` ABC in `zebra_agent.storage.interfaces` with methods: `initialize()`, `close()`, `add_entry(entry)`, `update_entry(entry)`, `soft_delete_entry(entry_id) -> bool`, `get_entry(entry_id) -> KnowledgeEntry | None`, `get_entries(user_id, category=None, include_deleted=False) -> list[KnowledgeEntry]`, `get_context_for_llm(user_id, limit=50) -> str`, `get_entries_for_verification(user_id, low_confidence_threshold=0.6, max_age_days=90, max_entries=5) -> list[KnowledgeEntry]`, and `find_contradicting_entry(user_id, category, key) -> KnowledgeEntry | None`.

The `delete_entry(entry_id) -> bool` method is **REMOVED** and replaced by `soft_delete_entry`.

#### Scenario: List entries by user excludes soft-deleted by default
- **WHEN** `get_entries(user_id=42)` is called and one entry has `deleted_at` set
- **THEN** only non-deleted entries belonging to `user_id=42` are returned

#### Scenario: List entries including soft-deleted when requested
- **WHEN** `get_entries(user_id=42, include_deleted=True)` is called
- **THEN** all entries including soft-deleted ones are returned

#### Scenario: LLM context excludes soft-deleted entries
- **WHEN** `get_context_for_llm(user_id=42)` is called and one entry is soft-deleted
- **THEN** the soft-deleted entry does not appear in the returned string

#### Scenario: Soft-delete marks entry as deleted
- **WHEN** `soft_delete_entry(entry_id)` is called for an existing entry
- **THEN** `True` is returned and the entry's `deleted_at` is set to the current UTC time

#### Scenario: Soft-delete non-existent entry returns False
- **WHEN** `soft_delete_entry(entry_id)` is called for an unknown ID
- **THEN** `False` is returned

#### Scenario: find_contradicting_entry returns existing entry with different value
- **WHEN** `find_contradicting_entry(user_id=1, category="facts", key="employer")` is called and an entry with that key exists with value "Acme"
- **THEN** the existing entry is returned

#### Scenario: find_contradicting_entry returns None for same value
- **WHEN** `find_contradicting_entry` is called with a key/value matching an existing entry exactly
- **THEN** `None` is returned (no contradiction)

#### Scenario: find_contradicting_entry ignores soft-deleted entries
- **WHEN** `find_contradicting_entry` is called and the only matching entry is soft-deleted
- **THEN** `None` is returned

#### Scenario: get_entries_for_verification returns low-confidence entries
- **WHEN** `get_entries_for_verification(user_id=42)` is called with entries below `low_confidence_threshold`
- **THEN** those entries are returned (up to `max_entries`)

### Requirement: Django ORM store implementation
The system SHALL provide `DjangoPersonalKnowledgeStore` implementing `PersonalKnowledgeStore` backed by `KnowledgeEntryModel`. All ORM calls SHALL be wrapped with `sync_to_async`. The `KnowledgeEntryModel` SHALL gain `time_sensitive` (BooleanField, default False) and `deleted_at` (DateTimeField, null=True) columns via a new Django migration.

#### Scenario: Persisted entries survive reinitialization
- **WHEN** an entry is added via `DjangoPersonalKnowledgeStore` and a new instance is created
- **THEN** `get_entries(user_id)` on the new instance returns the same entry

#### Scenario: Soft-deleted entry excluded from active queries after restart
- **WHEN** an entry is soft-deleted and a new `DjangoPersonalKnowledgeStore` instance is created
- **THEN** `get_entries(user_id)` does not return the soft-deleted entry

## ADDED Requirements

### Requirement: CATEGORY_DECAY_HALF_LIFE_DAYS constant
The system SHALL export a `CATEGORY_DECAY_HALF_LIFE_DAYS: dict[str, int | None]` constant from `zebra_agent.knowledge` mapping each category to its decay half-life in days (`history` maps to `None` meaning no decay).

#### Scenario: All categories have a half-life entry
- **WHEN** `CATEGORY_DECAY_HALF_LIFE_DAYS` is imported
- **THEN** every value in `KNOWLEDGE_CATEGORIES` has a corresponding key in the dict

## 1. Branch & Data Model

- [x] 1.1 Create branch `f32/knowledge-lifecycle` from master
- [x] 1.2 Add `time_sensitive: bool = False` and `deleted_at: datetime | None = None` fields to `KnowledgeEntry` in `zebra-agent/zebra_agent/knowledge.py`
- [x] 1.3 Add `CATEGORY_DECAY_HALF_LIFE_DAYS` constant to `zebra-agent/zebra_agent/knowledge.py`
- [x] 1.4 Update `KnowledgeEntry.create()` to accept `time_sensitive` parameter; update `to_dict()` / `from_dict()` for both new fields
- [x] 1.5 Add `time_sensitive` and `deleted_at` fields to `KnowledgeEntryModel` in `zebra-agent-web/`; run `makemigrations` then `ruff check --fix . && ruff format .`

## 2. Store Interface & Implementations

- [x] 2.1 Remove `delete_entry` and add `soft_delete_entry(entry_id) -> bool` to `PersonalKnowledgeStore` ABC in `zebra-agent/zebra_agent/storage/interfaces.py`
- [x] 2.2 Add `get_entries_for_verification(user_id, low_confidence_threshold, max_age_days, max_entries)` to ABC
- [x] 2.3 Add `find_contradicting_entry(user_id, category, key) -> KnowledgeEntry | None` to ABC
- [x] 2.4 Update `get_entries` signature to accept `include_deleted: bool = False`; update both `InMemoryPersonalKnowledgeStore` and `DjangoPersonalKnowledgeStore` to filter soft-deleted entries by default
- [x] 2.5 Implement `soft_delete_entry`, `get_entries_for_verification`, `find_contradicting_entry` in `InMemoryPersonalKnowledgeStore`
- [x] 2.6 Implement same three methods in `DjangoPersonalKnowledgeStore`
- [x] 2.7 Update web UI views to call `soft_delete_entry` instead of `delete_entry`

## 3. Tests for Store Changes

- [x] 3.1 Add unit tests for `KnowledgeEntry` new fields (`time_sensitive`, `deleted_at`, half-life constant)
- [x] 3.2 Add unit tests for `InMemoryPersonalKnowledgeStore`: soft-delete, `get_entries` with `include_deleted`, `get_entries_for_verification`, `find_contradicting_entry`
- [x] 3.3 Update existing `test_memory.py` and `test_knowledge.py` to remove `delete_entry` calls and use `soft_delete_entry`

## 4. Task Actions

- [x] 4.1 Create `zebra-tasks/zebra_tasks/knowledge/decay.py` — `DecayConfidenceAction` implementing half-life decay on `time_sensitive` entries
- [x] 4.2 Create `zebra-tasks/zebra_tasks/knowledge/add.py` — `AddKnowledgeAction` with contradiction detection and `next_route` routing
- [x] 4.3 Create `zebra-tasks/zebra_tasks/knowledge/verify.py` — `PickEntriesForVerificationAction` that selects entries needing human verification
- [x] 4.4 Register all three actions as entry points in `zebra-tasks/pyproject.toml` under `zebra.tasks`; run `uv sync --all-packages`
- [x] 4.5 Write unit tests for all three task actions in `zebra-tasks/tests/knowledge/`

## 5. Workflow YAML Files

- [x] 5.1 Create `zebra-agent/zebra_agent/workflows/knowledge_decay.yaml` — single `decay_confidence` task workflow
- [x] 5.2 Create `zebra-agent/zebra_agent/workflows/knowledge_verification.yaml` — pick entries → human task for each → apply result
- [x] 5.3 Create `zebra-agent/zebra_agent/workflows/resolve_contradiction.yaml` — human task presenting existing/proposed values → apply choice

## 6. Scheduled Routines

- [x] 6.1 Create `zebra-agent/zebra_agent/schedules/knowledge_lifecycle.py` — define `knowledge_decay_daily` and `knowledge_verification_weekly` routines
- [x] 6.2 Register both routines under `zebra.schedules` entry point in `zebra-agent/pyproject.toml`; run `uv sync --all-packages`
- [x] 6.3 Write unit tests confirming both routines are discovered by the registry

## 7. E2E Test

- [x] 7.1 Add e2e test in `zebra-agent-web/tests/` (or `zebra-agent/tests/`) that: creates two entries with conflicting values, calls `add_knowledge`, and asserts `next_route == "contradiction"`
- [x] 7.2 Extend e2e test to run `resolve_contradiction` workflow and verify the chosen resolution is persisted

## 8. Docs & CI

- [x] 8.1 Update `specs/zebra-as-is.md` to reflect lifecycle fields and new task actions
- [x] 8.2 Run `uv run ruff check --fix . && uv run ruff format .` and confirm `uv run pytest` is green
- [x] 8.3 Push branch to GitLab; verify CI pipeline (lint → unit → e2e) is green

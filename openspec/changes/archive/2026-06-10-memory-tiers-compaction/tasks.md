## 1. Branch Setup

- [x] 1.1 Create branch `f11/memory-tiers-compaction` from master

## 2. Data Model — Entry Types

- [x] 2.1 Add `tier: str = "hot"` field to `WorkflowMemoryEntry` in `zebra-agent/zebra_agent/memory.py` (include in `to_dict`/`from_dict`)
- [x] 2.2 Add `tier: str = "hot"` field to `ConceptualMemoryEntry` in `zebra-agent/zebra_agent/memory.py` (include in `to_dict`/`from_dict`)

## 3. MemoryStore Interface

- [x] 3.1 Add `CompactionBatch` dataclass to `zebra-agent/zebra_agent/storage/interfaces.py` (four lists: `warm_workflow`, `cold_workflow`, `warm_conceptual`, `cold_conceptual`)
- [x] 3.2 Add abstract `get_entries_for_compaction(now: datetime) -> CompactionBatch` to `MemoryStore` in `interfaces.py`
- [x] 3.3 Add abstract `apply_compaction_result(entry_id, tier, **fields)` methods (or a single `update_tier` method) to `MemoryStore` for updating tier + compressed fields in-place

## 4. InMemoryMemoryStore Implementation

- [x] 4.1 Implement `get_entries_for_compaction` in `InMemoryMemoryStore` — filter by age vs current tier using `timedelta(weeks=2)` and `timedelta(days=60)`
- [x] 4.2 Implement tier update methods in `InMemoryMemoryStore`

## 5. Django Data Model & Migration

- [x] 5.1 Add `tier = models.CharField(max_length=10, default='hot')` to `WorkflowMemoryModel` in `zebra-agent-web/zebra_agent_web/api/models.py`
- [x] 5.2 Add `tier = models.CharField(max_length=10, default='hot')` to `ConceptualMemoryModel` in `zebra-agent-web/zebra_agent_web/api/models.py`
- [x] 5.3 Run `uv run python manage.py makemigrations` then `uv run ruff check --fix . && uv run ruff format .` immediately after

## 6. DjangoMemoryStore Implementation

- [x] 6.1 Implement `get_entries_for_compaction` in `DjangoMemoryStore` — ORM query filtering by `timestamp` and `tier`
- [x] 6.2 Implement tier update methods in `DjangoMemoryStore`
- [x] 6.3 Update `add_workflow_memory` and `save_conceptual_memory` to persist the `tier` field

## 7. CompactMemoryAction Task Action

- [x] 7.1 Create `zebra-tasks/zebra_tasks/agent/compact_memory.py` with `CompactMemoryAction` class
  - Calls `memory_store.get_entries_for_compaction(now)`
  - For warm workflow entries: LLM call to compress `output_summary` + `effectiveness_notes` → digest ≤150 tokens; update tier
  - For cold workflow entries: clear both text fields; update tier
  - For warm conceptual entries: trim `recommended_workflows` to top 3; LLM compress `anti_patterns` ≤100 tokens; update tier
  - For cold conceptual entries: trim to top 1; clear `anti_patterns`; update tier
  - Degrades gracefully (logs + skips) if memory store absent or LLM fails per entry
- [x] 7.2 Register entry point in `zebra-tasks/pyproject.toml`: `compact_memory = "zebra_tasks.agent.compact_memory:CompactMemoryAction"`
- [x] 7.3 Run `uv sync --all-packages` to refresh entry points

## 8. Compact Memory Workflow

- [x] 8.1 Create `zebra-agent/workflows/compact_memory.yaml` — single-task workflow named `"Compact Memory"` calling `compact_memory` action

## 9. Routine & Management Command

- [x] 9.1 Create `zebra-agent-web/fixtures/routines/compact_memory.yaml` — schedule `0 */6 * * *`, `budget_aware: false`, `on_missed: run`, `workflow: Compact Memory`
- [x] 9.2 Create `zebra-agent-web/zebra_agent_web/api/management/commands/compact_memory.py` — runs one synchronous compaction pass via `AgentLoop` or direct action invocation

## 10. Tests

- [x] 10.1 Unit test `InMemoryMemoryStore.get_entries_for_compaction`: entries correctly classified into hot/warm/cold based on age and current tier
- [x] 10.2 Unit test `CompactMemoryAction`: mock memory store + LLM; verify warm workflow entries get LLM-compressed and tier updated; verify cold entries stripped; verify graceful degradation on LLM failure
- [x] 10.3 Unit test `CompactMemoryAction` for conceptual entries: warm trims to top 3 + compresses; cold trims to top 1 + clears
- [x] 10.4 Run full test suite: `uv run pytest zebra-agent/tests/ zebra-tasks/tests/ zebra-agent-web/tests/ --ignore=zebra-agent-web/tests/e2e_live --ignore=zebra-agent-web/tests/e2e -q`

## 11. Lint, Format, and Commit

- [x] 11.1 Run `uv run ruff check --fix . && uv run ruff format .`
- [x] 11.2 Run Zebra feedback: `bash scripts/zebra-feedback.sh 11 "Memory tiers compaction" "- hot/warm/cold tiering for WorkflowMemoryEntry and ConceptualMemoryEntry\n- CompactMemoryAction with LLM compression\n- Routine scheduler integration (every 6h)\n- manage.py compact_memory command"` (kimi unreachable — fixed run_goal to accept kimi)
- [x] 11.3 Commit: `feat: add hot/warm/cold memory tier compaction\n\nCloses #11`
- [x] 11.4 Push branch to GitLab and verify CI pipeline passes

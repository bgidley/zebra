## 1. Branch Setup

- [x] 1.1 Create branch `f105/fix-feedback-learning-loop` from master

## 2. MemoryStore Interface Extension

- [x] 2.1 Add abstract method `get_workflow_memory_by_run_id(run_id: str) -> WorkflowMemoryEntry | None` to `MemoryStore` in `zebra-agent/zebra_agent/storage/interfaces.py`
- [x] 2.2 Implement `get_workflow_memory_by_run_id` in `InMemoryMemoryStore` (`zebra-agent/zebra_agent/storage/memory.py`) — linear scan of `_workflow_memories`
- [x] 2.3 Implement `get_workflow_memory_by_run_id` in `DjangoMemoryStore` (`zebra-agent-web/zebra_agent_web/memory_store.py`) — `WorkflowMemoryModel.objects.filter(run_id=run_id).first()`

## 3. Fix UpdateConceptualMemoryAction Prompt

- [x] 3.1 In `zebra-tasks/zebra_tasks/agent/update_conceptual_memory.py`, extract non-empty `user_feedback` values from `wf_memories` and append them to the LLM prompt (e.g. `User feedback on recent runs:\n- <feedback>`)

## 4. Post-Feedback Conceptual Memory Refresh

- [x] 4.1 Add private method `_refresh_conceptual_memory(entry: WorkflowMemoryEntry, feedback: str) -> None` to `AgentLoop` in `zebra-agent/zebra_agent/loop.py` — reuses `get_provider` + `memory_store.save_conceptual_memory` pattern from `UpdateConceptualMemoryAction`
- [x] 4.2 Extend `AgentLoop.record_feedback()` to: call `get_workflow_memory_by_run_id`, and if found, schedule `asyncio.create_task(self._refresh_conceptual_memory(entry, feedback))`

## 5. Tests

- [x] 5.1 Unit test in `zebra-agent/tests/`: mock `MemoryStore` and LLM provider; assert `get_workflow_memory_by_run_id` is called and `save_conceptual_memory` is invoked after `record_feedback`
- [x] 5.2 Unit test for `UpdateConceptualMemoryAction` in `zebra-tasks/tests/`: verify user_feedback strings from `wf_memories` appear in the LLM prompt
- [x] 5.3 Unit test for `InMemoryMemoryStore.get_workflow_memory_by_run_id`: found and not-found cases
- [x] 5.4 Confirm all existing tests still pass: `uv run pytest zebra-agent/tests/ zebra-tasks/tests/ zebra-agent-web/tests/ --ignore=zebra-agent-web/tests/e2e_live --ignore=zebra-agent-web/tests/e2e -v`

## 6. Lint, Format, and Commit

- [x] 6.1 Run `uv run ruff check --fix . && uv run ruff format .`
- [ ] 6.2 Commit with message `fix: wire user feedback into conceptual memory refresh\n\nCloses #105`
- [ ] 6.3 Push branch to GitLab and verify CI pipeline passes (lint → unit → e2e)

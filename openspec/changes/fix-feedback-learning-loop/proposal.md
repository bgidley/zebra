## Why

When a user submits free-text feedback on a completed run, that feedback is saved to the
`WorkflowMemoryModel` row but never propagates into the conceptual memory index — the index
that the agent actually consults when choosing workflows for future goals. The learning loop
is therefore broken: user corrections have zero effect on future behaviour. Closes #105.

## What Changes

- `UpdateConceptualMemoryAction` is extended to include `user_feedback` from recent
  `WorkflowMemoryEntry` records in its LLM prompt (bug: the field was collected but silently
  dropped).
- A new `get_workflow_memory_by_run_id(run_id)` method is added to the `MemoryStore`
  interface (+ all implementations) so the feedback handler can retrieve the full entry.
- `AgentLoop.record_feedback()` is extended: after persisting the feedback text it
  triggers a lightweight conceptual-memory refresh for the affected workflow, so the
  conceptual index immediately reflects the user's correction.
- A new `refresh_conceptual_memory` task action is added (or inline method on `AgentLoop`)
  that encapsulates the post-feedback refresh logic without duplicating the existing
  `UpdateConceptualMemoryAction`.
- Tests cover the full path: feedback submitted → conceptual memory entry updated.

## Non-goals

- Real-time push/notification to the UI when conceptual memory is refreshed.
- Re-running conceptual memory for ratings (only free-text feedback is in scope).
- Changes to the Dream Cycle or any other workflow.

## Capabilities

### New Capabilities

- `feedback-learning-loop`: End-to-end path from user feedback submission to conceptual
  memory update, including the `MemoryStore.get_workflow_memory_by_run_id` interface method,
  the post-feedback refresh trigger in `AgentLoop`, and the corrected LLM prompt in
  `UpdateConceptualMemoryAction`.

### Modified Capabilities

_(none — no existing spec-level behaviour changes, only bug fixes within existing specs)_

## Impact

- `zebra-agent/zebra_agent/storage/interfaces.py` — new abstract method on `MemoryStore`
- `zebra-agent/zebra_agent/storage/memory.py` — `InMemoryMemoryStore` implementation
- `zebra-agent-web/zebra_agent_web/memory_store.py` — `DjangoMemoryStore` implementation
- `zebra-agent/zebra_agent/loop.py` — `AgentLoop.record_feedback()` extended
- `zebra-tasks/zebra_tasks/agent/update_conceptual_memory.py` — user feedback added to prompt
- New tests in `zebra-agent/tests/` and `zebra-agent-web/tests/`

## Context

`UpdateConceptualMemoryAction` runs at the end of every agent main loop execution (after
`assess_and_record`). It consults recent `WorkflowMemoryEntry` records but silently discards
the `user_feedback` field when building the LLM prompt. Separately, when a user later
submits free-text feedback via the web UI, `AgentLoop.record_feedback()` writes the text to
`WorkflowMemoryModel.user_feedback` but never re-triggers a conceptual memory update. The
result: the conceptual index — the only memory surface the agent reads at goal-selection
time — never reflects user feedback.

There is no `get_workflow_memory_by_run_id` method on `MemoryStore`, so the feedback path
cannot even look up the associated entry after writing.

## Goals / Non-Goals

**Goals:**
- `UpdateConceptualMemoryAction` passes `user_feedback` from recent `wf_memories` to the LLM.
- After `record_feedback()` persists feedback, a conceptual memory refresh is triggered for the affected workflow.
- `MemoryStore` gains `get_workflow_memory_by_run_id` so the feedback path can retrieve the entry.

**Non-Goals:**
- Rating-driven refresh (out of scope for this fix).
- Real-time UI notification of refresh completion.
- Changes to the Dream Cycle workflow.

## Decisions

### 1. Extend `UpdateConceptualMemoryAction` prompt rather than add a new action

The simplest fix: pass `user_feedback` strings from recent `wf_memories` into the existing
LLM prompt. No new code path, no new action, no entry-point registration. The action already
fetches `wf_memories`; we just need to surface `user_feedback` in the prompt text.

Alternative considered: a separate `RefreshConceptualMemoryAction`. Rejected — overkill for a
two-line data plumbing fix.

### 2. Trigger refresh inline in `AgentLoop.record_feedback()`, not via a new workflow

`record_feedback` already awaits `memory.update_user_feedback`. Extending it to also call a
private `_refresh_conceptual_memory_for_run()` method keeps everything in one place and avoids
spawning a full workflow for a lightweight LLM call.

The private method reuses `get_provider` and calls `memory_store.save_conceptual_memory`
directly — the same pattern used inside `UpdateConceptualMemoryAction`. This is acceptable
because `AgentLoop` is explicitly allowed to know about the LLM provider (it already wires
the provider into the workflow engine).

Alternative considered: running a mini one-task Zebra process. Rejected — adds process-
lifecycle overhead, complicates error surfacing, and doesn't align with XP simplicity.

### 3. Add `get_workflow_memory_by_run_id` to `MemoryStore` interface

Following the storage abstraction rule: any new data access path must go through the
interface, implemented in all backends. `InMemoryMemoryStore` scans its list; `DjangoMemoryStore`
does a `filter(run_id=...)` ORM query. No migration is required — the column already exists.

## Risks / Trade-offs

[Extra LLM call on feedback] → The refresh triggers an LLM call outside the main agent loop.
This costs a small amount of tokens per feedback submission. Mitigation: run it as a
fire-and-forget `asyncio.create_task` so the web response is not delayed; log and swallow any
failure (same graceful degradation as the rest of the loop).

[Conceptual memory written twice for a run] → The initial update (at end of the agent loop)
and the post-feedback refresh both write to the same conceptual concept entry. The second
write is an update (not an append), so the final state is correct. The only risk is a brief
window where the index doesn't yet include feedback — acceptable.

[Interface change propagates to all backends] → Adding `get_workflow_memory_by_run_id`
requires implementations in `InMemoryMemoryStore` and `DjangoMemoryStore`. Both are in this
repo; no external consumers of the interface exist yet.

## Migration Plan

No migrations needed. `WorkflowMemoryModel.user_feedback` already exists (migration 0004).
The changes are purely additive: a new interface method + extended prompt + new call path.

Deploy by merging to master as normal; the daemon picks up the new behaviour immediately.

## Open Questions

None.

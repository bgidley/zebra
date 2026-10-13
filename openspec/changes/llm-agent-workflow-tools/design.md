## Context

See `specs/llm-agent-tools-design.md` for the narrative design. Issue #146.

## Decisions

1. **Suspension is an engine feature, not an action trick.** An action returns `TaskResult.suspend(children)`; the children are processes it created (in `CREATED`, linked by `parent_process_id`/`parent_task_id`). The engine persists `AWAITING_SUBFLOW` + `__pending_subflows__` on the task *before* starting the children, so a crash in between is recoverable.
2. **Results are computed at resume time from the child processes**, not pushed into the task. `__pending_subflows__` stays on the task until the resumed run finishes, so a crash mid-resume re-runs with the same results.
3. **Children are started after the parent's lock is released.** Locks are re-entrant per engine and the inner release would drop the outer lock, so a parent is never resumed nested inside its own transition. A child-terminal hook flips the parent task to `READY`; if this engine is already driving the parent process it leaves the run to that driver, otherwise it calls `transition_task`.
4. **Tools are workflows; `define_workflow` is a workflow too.** No inline creation path: it runs *Define Workflow* (ethics gate → `workflow_creator`) as a subflow like any other tool.
5. **`inputs:` lives in `ProcessDefinition.properties`** (like `result_key`), so no model change and it is JSON-serializable.
6. **Tool names are slugs** (`web_research`) mapped to workflow names, because provider tool names cannot contain spaces.
7. **Cost roll-up in the action**: on resume, each child's `__total_cost__`, `__total_tokens__` and `__token_history__` are added to the calling process, so `execute_goal_workflow` reports the full cost.

## Risks / Trade-offs

- Children run inline in the same call stack (as `subworkflow` does), so a goal's wall clock still bounds tool calls via `start_process_with_timeout`. Not holding a coroutine applies to the *task*, which is what makes human-in-the-loop tools and restarts work.
- Failing a parent does not cancel its running children; their completion is ignored because the parent task is no longer `AWAITING_SUBFLOW`.
- `tool_tags` lists are capped and ranked by `success_rate` (answers the open question) to keep the tool list small.

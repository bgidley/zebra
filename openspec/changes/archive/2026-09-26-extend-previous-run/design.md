## Context

The Agent Main Loop passes `{{goal}}` to every step. A follow-up needs the previous run's goal and output to reach the steps that reason about the goal, without altering what gets recorded and displayed as the goal.

## Decisions

- **Carry context in its own property instead of rewriting `goal`.** If `goal` included the context, run records and the Activity list would show it, and following up on a follow-up would nest each earlier context inside the next. The context is added only when a prompt or sub-workflow goal is built, by `with_previous_run(goal, properties)`. That keeps the format in one place and needs no YAML or template changes, so goals queued before the deploy still work.
- **Propagate to the executed workflow.** `execute_goal_workflow` passes the annotated goal to the sub-workflow. Most runs reuse an existing workflow that only reads `{{goal}}`, so without this the follow-up would run without its context.
- **The ethics gate judges the combined request.** The input gate and plan review both see the previous run. The audit record keeps the plain goal.
- **Delimit the previous output.** It is wrapped in `<previous_run>` tags and truncated to 2,000 characters, which limits prompt growth and makes clear it is data, not instructions.
- **Check ownership at the store.** `DjangoMetricsStore.get_run` hides runs owned by a *different* user than the current-user contextvar. Unowned runs stay visible: API submissions and pre-namespacing rows have no `user_id`, and strict `user_id = me` scoping made their pages and status polling 404 (it broke the e2e golden path). The daemon and other system paths, which have no user, stay unfiltered, matching `get_recent_runs`/`get_completed_runs`. This also protects `run_detail` and the REST run endpoints.
- **Only completed runs can be extended.** `_completed_run()` rejects runs that are unknown, belong to someone else, or are still running. The form and the preview endpoint behave the same.

## Risks / Trade-offs

- The previous output can include untrusted web content from earlier searches. It is delimited and truncated, and the ethics gate sees it, but it is still shown to the LLM.
- Activity rows for orphaned processes (no run record) show "Extend", but it has nothing to attach and opens a plain form.

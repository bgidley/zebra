## Why

Follow-up goals ("now make it shorter", "do the same for Q4") need the context of an earlier run, and users currently have to paste it back in. The first F116 cut only fed that context to the workflow selector and creator. The workflow that actually ran never saw it, and anyone with a run ID could read another user's run output through the new endpoints. Closes #116.

## What Changes

- Users can attach one of their own completed runs to a new goal. They can do this from the goal form (a dropdown of their 10 most recent runs, with a preview) or from an "Extend" link in the Activity list, which works for runs of any age.
- The entry points (`AgentLoop.process_goal`, `queue_goal`) store a compact `previous_run_context` process property: run ID, goal, workflow name, outcome, and output truncated to 2,000 characters.
- A shared helper, `zebra_tasks.agent.followup.with_previous_run()`, adds that context to the goal for every step that reasons about it: the ethics gate, workflow selector, workflow creator, variant creator, and the executed workflow (via `execute_goal_workflow`). The plain `goal` property is unchanged.
- `WorkflowRun` gains `extends_run_id`, recorded by `assess_and_record` and `record_metrics`. The run detail page links to the extended run.
- `DjangoMetricsStore.get_run` is scoped to the current user, as the other read methods already are.

## Capabilities

### New Capabilities
- `goal-follow-up`: attach a previous run to a new goal, propagate its context, and record the lineage.

### Modified Capabilities
<!-- none -->

## Non-goals

- Chaining more than one previous run, or extracting context automatically from memory.
- Editing or summarising the previous output before it is attached. It is truncated, not summarised.
- A CLI flag for follow-ups. The `process_goal` parameter makes one easy to add later.

## Impact

- `zebra-tasks`: new `agent/followup.py`, plus call sites in the selector, creator, variant creator, ethics gate, executor, `assess_and_record` and `record_metrics`.
- `zebra-agent`: `WorkflowRun.extends_run_id`, the `process_goal` parameter, and the in-memory store.
- `zebra-agent-web`: `WorkflowRunModel.extends_run_id` (migration 0023), `get_run` scoping, goal form, `/runs/<id>/context/`, Activity "Extend" link, and run detail link.

## Why

A continuation only gives the executed workflow the previous run as text appended to `goal` (output capped at 2000 chars, each task's output at 300). A workflow cannot reach the previous run's own values. Prod's *Web Research* (v4, dream-evolved) declares a `prior_brief` input so a refinement can reuse the earlier research brief, but nothing ever fills it: Web Research was continued in 50% of refinement requests and re-derived the brief each time, and *Gear Requirements Gathering* continuations re-ran "Search the web" and "Summarise results" by hand. Issue #222 (dream request, refs #189).

## What Changes

- **`prior_outputs` on continuations.** When `execute_goal_workflow` starts the goal workflow for a goal that continues a run (`previous_run_context.run_id`), it finds that run's goal-workflow process (completed or failed) and passes its workflow properties to the new child as the `prior_outputs` dict. Engine bookkeeping (`__*`), `goal` and an earlier `prior_outputs` are left out. A string longer than 8000 chars is cut to 8000; any other value whose JSON is longer than that is dropped; a value that would take the total past 32000 chars is left out. Templates read it as `{{prior_outputs.<key>}}`, which is empty when there is no prior run or no such key.
- **`from_prior` input binding.** An input in the workflow's `inputs` schema can declare `from_prior: <key>`. On a continuation the input is set from `prior_outputs[<key>]`, so existing `{{input}}` templates work unchanged (e.g. `prior_brief: {type: string, from_prior: research_brief}`). An input the goal already set is never overwritten.
- **Workflow authors learn it.** The workflow creator's and optimizer's prompts say how to use `prior_outputs` and `from_prior`, so dream-made workflows can adopt them.
- Best-effort: when the prior process can't be found (pruned, or a run older than its processes), the continuation runs as before, with a warning in the log.
- A retry that resumes (#187) is unchanged. It already carries the failed process's properties, and now also gets `prior_outputs`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `goal-continuation`: continuations expose the previous run's outputs to the executed workflow.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A continued workflow can read the previous run's outputs | Test: run *A* whose goal workflow sets `research_brief`; a continuation of *A* runs a workflow whose task prompt is `{{prior_outputs.research_brief}}` → the task sees the brief. A non-continuation gets no `prior_outputs` (the template is empty) |
| O2 | A declared input binds to a prior output without changing its prompts | Test: input `prior_brief` with `from_prior: research_brief` → the child's `prior_brief` property is the earlier brief; when the prior run lacks the key the input stays unset |
| O3 | Big or internal values don't bloat the child | Tests: `__*` keys, `goal` and nested `prior_outputs` are excluded; an over-long string is cut to the cap; an over-long list is dropped; the total stays within the cap |
| O4 | A missing prior process never breaks a continuation | Test: a `previous_run_context` whose run has no process → the goal workflow still runs, without `prior_outputs`, and a warning is logged |
| O5 | Workflow authors and docs know about it | The creator and optimizer prompts mention `prior_outputs` / `from_prior` (asserted in a test); `zebra-tasks/AGENTS.md` (`ExecuteGoalWorkflowAction`) and `specs/zebra-as-is.md` describe it |

## Impact

- Changed: `zebra-tasks/zebra_tasks/agent/execute_workflow.py`, `zebra-tasks/zebra_tasks/agent/followup.py`, `zebra-tasks/zebra_tasks/agent/creator.py`, `zebra-tasks/zebra_tasks/agent/optimizer.py`, their tests, `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`.
- No migrations, settings or API changes. Workflow YAML gains an optional `from_prior` keyword on an input; JSON Schema ignores unknown keywords, so `llm_agent` tool parameters are unaffected.
- Prod's dream-made *Web Research* needs `from_prior: research_brief` on its `prior_brief` input (or `{{prior_outputs.research_brief}}`) to benefit. That is a library edit, left to the dream cycle or a person.

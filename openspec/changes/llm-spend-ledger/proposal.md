## Why

The daily budget sums `WorkflowRun.cost`, which `assess_and_record` sets to the goal workflow's
own spend only. The Agent Main Loop's calls (selection, ethics gates, assessment, memory,
knowledge) are missed, and so is all spend outside goals: Dream Cycle, routines, postmortems,
outcome reviews, goals that fail before a run is recorded. On prod a goal that spent $0.038
recorded $0. Closes #206.

## What Changes

- **Spend ledger**: every LLM call made through `get_llm(model, context)` appends an entry
  (time, cost, tokens, model, process) to the metrics store. New `MetricsStore.record_llm_spend`,
  in-memory and Django (`zebra_llm_spend`, migration 0032). A ledger write never fails the call.
- **Budget = ledger**: `MetricsStore.get_total_cost_since` sums the ledger, so every call counts
  exactly once wherever it ran.
- **Run totals**: when a goal finishes (daemon or `AgentLoop`), its `WorkflowRun` gets the root
  process's final `__total_cost__` and tokens (`MetricsStore.update_run_totals`).

## Non-goals

- Back-filling spend from before the change; per-user budgets.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every LLM call made with a context is in the spend ledger | Tests: a call through `get_llm(model, context)` adds one ledger entry with its cost, tokens, model and process; a failing ledger write does not fail the call |
| O2 | The daily budget counts all LLM spend, not just goal workflows | Tests: `get_total_cost_since` sums ledger entries since the reset (in-memory and Django); prod: after a goal and a Dream Cycle, today's budget spend equals the sum of their processes' `__total_cost__` |
| O3 | A finished goal's run record shows its real cost | Tests: daemon and `AgentLoop` completion set `WorkflowRun.cost` / tokens to the root process totals; prod: a new goal's run page cost equals its process `__total_cost__` (no more $0 for a paid run) |
| O4 | Nothing else changes for stores or callers | Third-party `MetricsStore` subclasses keep working (new methods have defaults); full unit suite and e2e green |

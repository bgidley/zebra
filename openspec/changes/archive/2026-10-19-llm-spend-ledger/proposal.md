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
| O1 | Every LLM call made with a context is in the spend ledger, once | Tests: a call through `get_llm(model, context)` adds one entry with cost, tokens, model and process; calls in a parent and its subflow each appear once; a failing ledger write is logged and does not fail the call. Context-free calls are listed in the design (AgentLoop's writes directly; two hand-run commands are excluded) |
| O2 | The daily budget counts all LLM spend, not just goal workflows | Tests: in an isolated engine run with a subflow, budget == ledger sum == the calls' reported costs; reset-instant boundary in the in-memory and Django stores |
| O3 | A finished goal's run record shows its real cost | Tests: the daemon's finish hook and `record_run_totals` set the run to the ledger total of its process tree (fallback without a ledger); prod: a goal finished after deploy has run cost equal to the ledger sum for its processes, not $0 |
| O4 | Custom `MetricsStore` implementations keep working | The new methods have defaults (not abstract), tested; full unit suite and e2e green |

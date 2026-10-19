## Context

The budget summed `WorkflowRun.cost` (goal workflow only). Full design:
`specs/llm-spend-ledger-design.md`.

## Decisions

- **Data model**: new table `zebra_llm_spend` (migration 0032), one row per LLM call.
- **Interfaces**: `MetricsStore.record_llm_spend`, `get_spend_for_processes`,
  `update_run_totals` (concrete defaults so custom stores keep working); `get_total_cost_since`
  sums the ledger. `zebra_tasks.llm.usage.record_spend`; `zebra_agent.metrics.record_run_totals`.
- **Write path**: the recording LLM from `get_llm(model, context)` writes the ledger after each
  call; failures are logged, never raised.
- **Run totals**: ledger sum over the run's process tree, because per-process `__total_cost__`
  double counts (subflows inherit parent properties; `llm_agent` rolls children up).
- **API / UI**: none new; run pages show the corrected cost.

## Risks / trade-offs

- Hand-run management commands without a task context are not in the ledger.
- A failed ledger write is lost from the budget (logged).

## as-is updates

`specs/zebra-as-is.md` MetricsStore and BudgetManager paragraphs; new design doc.

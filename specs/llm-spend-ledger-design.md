# LLM spend ledger (#206)

## 1. Goal and scope

Make the daily budget and run records count all LLM spend. Before, the budget summed
`WorkflowRun.cost`, which `assess_and_record` set to the goal workflow's own spend: the Agent
Main Loop's calls, retries, and everything outside goals (Dream Cycle, routines, postmortems,
outcome reviews, goals failing before a run record) were missed. On prod a goal that spent
$0.038 recorded $0. Issue [#206](https://gitlab.com/gidley/zebra/-/work_items/206).

Not in scope: back-filling spend from before the change; per-user budgets.

## 2. Data model

Table `zebra_llm_spend` (`LLMSpendModel`, migration `0032_llm_spend`): `occurred_at`
(indexed), `cost` (Decimal 12,8), `input_tokens`, `output_tokens`, `model`, `process_id`
(indexed). One row per LLM call. In-memory store keeps a list.

Per-process `__total_cost__` is not a safe sum across a run: a subflow inherits its parent's
properties (its `__total_cost__` starts at the parent's), and `llm_agent` rolls tool children
into its parent. The ledger holds each call once, so sums over it are exact.

## 3. Interfaces

| Piece | What it is |
|---|---|
| `MetricsStore.record_llm_spend(*, cost, input_tokens, output_tokens, model, process_id, at)` | Append one call. Default no-op |
| `MetricsStore.get_total_cost_since(since)` | Now the ledger sum (`occurred_at >= since`) |
| `MetricsStore.get_spend_for_processes(ids)` | `(cost, input, output)` over those processes; default `None` (no ledger) |
| `MetricsStore.update_run_totals(run_id, *, cost, input_tokens, output_tokens)` | Overwrite a run's cost/tokens; default `False` |
| `zebra_tasks.llm.usage.record_spend(context, response)` | Called by the LLM `get_llm(model, context)` returns, after `record_usage`; uses `context.extras["__metrics_store__"]`; logs and swallows failures |
| `zebra_agent.metrics.record_run_totals(metrics, store, process)` / `run_process_ids(store, root)` | Run totals = ledger sum over the root and its descendants (max 500); without a ledger, root `__total_cost__` + `execution_result.cost`. Never raises |

## 4. Control flow

Every LLM call with a task context: `record_usage` (process properties) then `record_spend`
(ledger). `AgentLoop`'s own conceptual-memory call has no context and writes the ledger
directly. The daemon's `_record_finished` and `AgentLoop._run_agent_workflow` (COMPLETE or
FAILED) call `record_run_totals` once the goal ends.

## 5. Configuration

None. The engine's `__metrics_store__` extra (set by `AgentLoop`) is the ledger.

## 6. Open questions / risks

- Two hand-run management commands (`bootstrap_values_taxonomy`, `compact_memory`) call an LLM
  without a task context and are not in the ledger; the scheduled Compact Memory routine runs
  as a workflow and is.
- A failed ledger write is logged as a warning, not retried: that call is missing from the
  budget.
- Spend from before the deploy is not in the ledger, so the day of the deploy under-counts
  until the next reset.
- A goal parked on a human task and finished later through the web gets run totals only via the
  daemon's reconcile (daemon goals) or the next `AgentLoop` poll.

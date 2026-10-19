Branch: `f206/spend-ledger`

## 1. Ledger

- [x] 1.1 `MetricsStore.record_llm_spend` / `get_spend_for_processes` / `update_run_totals` (defaults); `get_total_cost_since` sums the ledger
- [x] 1.2 In-memory store; Django `LLMSpendModel` + migration 0032 + store
- [x] 1.3 `record_spend` after every `get_llm(model, context)` call; `AgentLoop` memory call writes directly

## 2. Run totals

- [x] 2.1 `record_run_totals` / `run_process_ids`; daemon `_record_finished` and `AgentLoop` call it

## 3. Tests, docs

- [x] 3.1 Tests: ledger write and failure, reset boundary (both stores), process-tree budget == ledger == run total, fallback, daemon hook, interface defaults
- [x] 3.2 `specs/llm-spend-ledger-design.md`, `specs/zebra-as-is.md`, AGENTS.md files
- [x] 3.3 Run lint + format (`uv run ruff check --fix . && uv run ruff format .`), full unit suite

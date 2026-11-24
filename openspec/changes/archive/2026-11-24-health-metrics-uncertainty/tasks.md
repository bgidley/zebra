## 1. Statistics
- [x] 1.1 Add `wilson_interval` and a confidence-label helper to `zebra-agent/zebra_agent/metrics.py`, with tests
## 2. Analyzer
- [x] 2.1 Add interval and `confidence` to `_workflow_stats`; emit zero-run workflows; add `workflows_without_runs`
- [x] 2.2 Rework high/low performer categorisation; apply the interval to tool stats
- [x] 2.3 Tests in `zebra-tasks/tests/` for O1-O3, O5
## 3. Evaluator
- [x] 3.1 Render `s/n`, interval and sufficiency tag in the prompt; add the "do not judge thin data" instruction
- [x] 3.2 Prompt-building tests (O4); check consumers tolerate `success_rate: None`
## 4. Docs
- [x] 4.1 Update `specs/zebra-as-is.md` and run `ruff check --fix` / `ruff format`

# Tasks

Branch: `f150/history-continuation-trigger`. Commits reference #150.

## 1. Keyword search

- [x] 1.1 Add `search_keywords()` to `zebra-agent/zebra_agent/storage/interfaces.py` and use it in `InMemoryMetricsStore.search_runs`; verify with new tests in `zebra-agent/tests/test_metrics.py`
- [x] 1.2 Use it in `DjangoMetricsStore.search_runs` (OR of `goal__icontains`); verify with new tests in `zebra-agent-web/tests/unit/test_metrics_search_runs.py`

## 2. History-need decision

- [x] 2.1 `AssessHistoryNeedAction`: include the continuation comment and previous goal, skip the cue gate for continuations, extend the cues, and ask for topic keywords in the prompt; verify with new tests in `zebra-tasks/tests/test_workflow_history.py`

## 3. Delivery

- [x] 3.1 Update `specs/zebra-as-is.md`; run `openspec validate history-continuation-trigger --strict`
- [ ] 3.2 Run lint, format and the test suites; get CI green; run Zebra feedback; merge `Closes #150`

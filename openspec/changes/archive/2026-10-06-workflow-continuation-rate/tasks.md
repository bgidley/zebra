## 1. Metrics

- [x] 1.1 Add `continued_runs` field and `continuation_rate` property to `WorkflowStats`
- [x] 1.2 Populate `continued_runs` in `InMemoryMetricsStore.get_stats` / `get_all_stats`
- [x] 1.3 Populate `continued_runs` in `DjangoMetricsStore.get_stats` / `get_all_stats` via subquery-filtered `Count`

## 2. Web UI and API

- [x] 2.1 "Continued" stat card on the workflow detail page
- [x] 2.2 "N% continued" on dashboard top workflows and the workflow library list
- [x] 2.3 `continued_runs` / `continuation_rate` in API workflow stats and `WorkflowStatsSerializer`

## 3. Tests and docs

- [x] 3.1 Store tests (in-memory and Django), view/template/serializer tests
- [x] 3.2 Update `specs/zebra-as-is.md`

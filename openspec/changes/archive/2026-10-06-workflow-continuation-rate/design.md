## Context

Lineage is persisted on `WorkflowRun.extends_run_id` (#116/#134). The #136 analyzer counts a run as continued when some run's `extends_run_id` points at it, but only within the dream window.

## Decisions

**Same definition everywhere.** `continued_runs` = runs of this workflow that at least one later run continues. A run continued twice counts once, so the rate is bounded by 1 and matches the analyzer.

**Computed in the stores, not the views.** `WorkflowStats` is the store's existing aggregate, so a defaulted field keeps the `MetricsStore` contract backward compatible (custom stores report 0). Django uses `Count("id", filter=Q(id__in=<extends_run_id subquery>))` in the same aggregate query as the other stats: no extra round trip, no migration.

**Show it only where it means something.** List rows add "N% continued" only for workflows with continued runs; the detail page always shows the card.

**Dream `continuation_changes` stays on the dream run page.** The dream cycle records as a normal run, so its summary (with the #136 "Continuations" section) and optimizer output already render on its run detail page; no new page.

## Risks

- The subquery isn't user-scoped; continuation is only allowed on your own runs (#134), so in practice counts are per-user.

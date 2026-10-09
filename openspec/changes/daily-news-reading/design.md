# Design

## Context

- `SchedulerLoop._dispatch` either runs the goal-queue tick (`workflow: null`) or creates and starts
  a workflow process directly.
- Goals are Agent Main Loop processes in `CREATED` state, created by
  `zebra_agent_web.api.goals.queue_goal` and run by the budget daemon.
- Kagi News publishes a public JSON feed:
  - `https://news.kagi.com/kite.json` → `{timestamp, categories: [{name, file}]}`.
  - `https://news.kagi.com/<file>` → `{category, timestamp, clusters: [...]}`. Each cluster has
    `title`, `short_summary`, `talking_points`, `did_you_know`, `articles: [{link, domain, title}]`
    and more.

## Decisions

1. **Goal, not workflow.** A routine with `goal` is queued like a user goal. It gets budget pacing,
   ethics gates, metrics, the Activity view and continuation for free. `zebra-agent` must not import
   the web package, so the loop takes a `queue_goal_fn(routine)` callable. Without one, it logs
   `[scheduler:skip]`.
2. **No pile-up.** Before queueing, the loop checks `CREATED` and `RUNNING` processes for
   `__routine__ == routine.name`. If one is found, it skips with status `already_queued`. The cron
   schedule gives at most one run a day.
3. **Run as the owner.** Knowledge is scoped to `user_id`. The daemon resolves `run_as` (a
   username) or the first active superuser, plus the installation identity. If there is no user,
   the goal still runs but `store_learned_knowledge` skips with `no_user`.
4. **Requested workflow.** The goal carries `requested_workflow: "Daily News Reading"`. The
   selector honours it when the workflow is in the library, which avoids the LLM drifting to *Web
   Research*. If the workflow is missing, normal LLM selection runs.
5. **Reading.** Kagi Extract takes a list of pages, so one call reads all picks. Per-page errors,
   a missing `KAGI_API_KEY` or an HTTP failure all fall back to the cluster's summary and talking
   points, so a paywall never fails the goal. A feed outage fails `kagi_news_fetch`, which fails
   the goal cleanly.
6. **World knowledge.** A new `world` category reuses `store_learned_knowledge`, the F152 path with
   validation, caps and confidence ceiling. Keys are story topics (`snake_case`). With
   `update_agent_entries: true`, a changed agent-sourced value is updated in place: the story moved
   on, which is not a dilemma. Conflicts with `source=human` entries still start *Resolve Knowledge
   Contradiction*.

## Risks

- `kite.json` is an undocumented feed. The action validates its shape and fails with a clear error.
- The LLM may return fewer or more than 5 picks. `kagi_news_read` takes the first 5 valid ids.

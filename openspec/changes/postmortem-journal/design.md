## Context

Failed goal runs already flow through `assess_and_record` (#140). Goals failed by the timeout
(#142) or a crash end FAILED without reaching it. Memory retrieval is goal-relevant via
`MemoryStore.search_*` (#169). Lessons must reach both the workflow selector and the executed
goal workflow, like workflow history (F138) and help guidance (#176).

## Decisions

- **Storage**: a third memory kind, `PostmortemEntry` (`zebra_postmortems`), not personal
  knowledge: lessons are about how Zebra works, not about the user. Scoped by `user_id` like the
  other memory tables. Embedded on the goal text for vector search; default search is keyword
  overlap on goal + lesson over the 50 most recent.
- **One action, three triggers**: `write_postmortem` runs inline in the main loop for failed runs.
  Timeouts / crashes and low ratings start a one-task system workflow *Postmortem* with the same
  action, so the LLM call is costed and journalled like any process.
- **Dedup**: one postmortem per `run_id` (`get_postmortem_by_run_id`). A failed run later rated
  1 keeps its failure postmortem.
- **When the loop already handled it**: the daemon/`AgentLoop` hook skips processes that are not
  Agent Main Loop runs, that ran the `write_postmortem` step, or that were cancelled by the kill
  switch.
- **Low rating** (1 or 2): started as a background task from `AgentLoop.record_rating` so rating
  stays instant. Uses the run's goal, workflow, error and the user's feedback.
- **No LLM → no lesson**: a lesson without a root cause is noise; the action stores nothing.
- **Retrieval**: `consult_memory` adds up to 3 lessons; `lessons_context` goes into
  `memory_context` and `with_lessons` appends it to the child goal.

## Risks

- Lessons may be wrong. They are advisory context only, shown in the journal so a human can see
  them; deletion/curation is left for a follow-up.
- Extra haiku call per failure (~$0.001); timeouts already cost far more.

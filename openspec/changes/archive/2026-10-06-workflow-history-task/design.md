# Design

## Context

- `WorkflowRun` records live in `MetricsStore` (`InMemoryMetricsStore`, `DjangoMetricsStore`). The
  Django store already scopes queries to `get_current_user_id()`. `started_at` is indexed;
  `goal` / `output` / `error` are `TextField`s (CLOBs on Oracle).
- Task actions get the store from `context.extras["__metrics_store__"]`.
- `agent_main_loop.yaml` (v8) runs `consult_memory → consult_knowledge → ethics_input_gate → …`.
  Context reaches the executed child workflow only through its `goal`: F116's
  `with_previous_run()` in `zebra_tasks/agent/followup.py` appends previous-run context.

## Goals / Non-Goals

**Goals:** a reusable deterministic fetch task; a cheap decision step; zero extra cost for goals
that don't mention history. See proposal.md for scope and non-goals.

**Non-Goals:** changing how memory or knowledge are consulted; making existing workflows read a
new property (they keep consuming `goal`).

## Decisions

1. **Two actions, not one.** `assess_history_need` (decides and extracts filters) is separate from
   `get_workflow_history` (pure fetch). The fetch is reusable in any YAML workflow with literal or
   templated filters. *Alternative:* one LLM-driven action. Rejected because it couples fetching to
   an LLM and can't be used deterministically.
2. **Keyword pre-check before the LLM.** A small regex over the goal looks for cues such as
   `last week|yesterday|before|previous|history|did I|have we|earlier|ago|since|<month names>`.
   If none match, the action routes `no_history` with no LLM call, mirroring
   `assess_continuation`'s pass-through. When cues match, a Haiku call returns JSON:
   `{needs_history, since, until, text, reasoning}`. *Alternative:* always call the LLM. Rejected
   because it adds cost and latency to every goal.
3. **New store method `search_runs(since, until, text, workflow_name, success, limit)`.** It is
   added to the `MetricsStore` ABC. Django uses `goal__icontains` on Oracle, which becomes
   `UPPER(...) LIKE` on a CLOB: acceptable at our run volume, and the date filter narrows the
   rows first. Text matches **goal only** in v1, because searching output CLOBs is slow and noisy.
   *Alternative:* Oracle Text index. Rejected for v1 as unnecessary.
4. **Relative-time parser** (`-7d`, `24h`, `30m`, `2w`) lives in the history module. An unsigned
   offset means the past. Times are normalised to UTC-aware datetimes.
5. **Bounded output.** Per-run `output` / `error` are truncated to about 300 characters, and
   `history_context` is capped at about 4,000 characters. The list is newest first and truncation
   is marked with an ellipsis note. Keeps process properties and prompts small.
6. **Explicit `user_id` on `search_runs`.** The daemon executes goals with no request user, so
   relying on `get_current_user_id()` alone would expose every user's history. The action passes
   the process's `__user_id__`; the Django store uses it, or falls back to the request user. The
   single-user in-memory store ignores it.
7. **Exclude the current run.** The current `run_id` process property is filtered out so a run
   doesn't see itself as history.
8. **Wiring.** Main loop v9: `consult_knowledge → assess_history_need`; on `needs_history` it
   goes to `get_workflow_history → ethics_input_gate`; on `no_history` it goes straight to
   `ethics_input_gate`. History outputs to the `workflow_history` key. The selector gets a new
   optional `history_context` input. `execute_goal_workflow` appends a delimited
   `## Workflow history` section after `with_previous_run()` when
   `workflow_history.history_context` is present.

### Interface summary (for zebra-as-is.md §4 Catalogue, §5 Agent main loop / Metrics)

- Store: `MetricsStore.search_runs(...)`, an abstract method that both implementations provide.
  **No DB migration.**
- Actions: `get_workflow_history`, `assess_history_need` (entry points in `zebra-tasks`), both
  `reversibility_hint = always_reversible`.
- YAML: `agent_main_loop.yaml` v9 adds two tasks and three routings, plus a new `history_context`
  property on `select_workflow`.

## Risks / Trade-offs

- [Wrong extraction: the LLM picks bad dates or text] → the fetch echoes `filters` into
  `history_context` so downstream LLMs can see what was searched; a missed fetch means no history,
  not a failure.
- [CLOB `LIKE` gets slow as history grows] → the date window and limit bound the scan; revisit
  with Oracle Text if needed.
- [Keyword false negatives skip a needed fetch] → the cue list is easy to extend; workflows can call
  `get_workflow_history` directly.
- [Prompt bloat] → hard size caps (Decision 5).
- [Third-party `MetricsStore` subclasses break on a new abstract method] → no in-repo subclasses
  beyond the two; note it in the changelog.

## Migration Plan

No schema migration. Deploy normally; rolling back means reverting the YAML to v8 (the actions are
inert unless referenced).

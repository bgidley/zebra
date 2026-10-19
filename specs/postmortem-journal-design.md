# Postmortem journal (#175)

## 1. Goal & scope

After an incident Zebra writes down what happened, the root cause and the lesson, stores it in
long-term memory, and recalls it when a later goal is similar. The journal is browsable in the UI
in Zebra's own voice. GitLab: [#175](https://gitlab.com/gidley/zebra/-/issues/175).

Incidents:

| Trigger | When | Where it runs |
|---------|------|---------------|
| `failure` | The goal workflow failed (after any #176 help requests; `assess_and_record` has run) | `write_postmortem` step in the Agent Main Loop |
| `timeout` | An Agent Main Loop process ended FAILED without reaching that step (goal timeout #142, crash, gate error) | *Postmortem* system workflow, started by the daemon (`_tick` → `_record_finished`) and `AgentLoop._run_agent_workflow` |
| `low_rating` | The user rates a run 1 or 2 | *Postmortem*, started in the background by `AgentLoop.record_rating` |

Not in scope: editing/deleting lessons, decaying old lessons, deduplicating similar lessons,
postmortems for non-goal processes (Dream Cycle, routines), and kill-switch cancellations (stopped
on purpose).

## 2. Data model

- `PostmortemEntry` (`zebra_agent/memory.py`): `id, timestamp, run_id, goal, workflow_name,
  trigger, what_happened, root_cause, lesson, voice, confidence, user_id`.
- `MemoryStore`: abstract `add_postmortem`, `get_recent_postmortems(limit)`,
  `get_postmortem_by_run_id(run_id)`; `search_postmortems(goal, limit=3)` defaults to keyword
  overlap on goal + lesson over the 50 most recent and returns only overlapping entries.
- Django: `PostmortemModel` → `zebra_postmortems` (migration `0028_postmortems`), scoped by
  `user_id` (entry's `user_id`, from the goal's `__user_id__`, else the request user, else the
  run's). Oracle adds `embedding VECTOR` on the goal (`EMBEDDED_TABLES`, trigger
  `zebra_pm_embed_trg`); `search_postmortems` uses `VECTOR_DISTANCE` like #169.
- One postmortem per `run_id`: `run_id` is unique and NULL when there is no run (Oracle has no conditional unique constraints; migration 0029), so racing triggers (daemon timeout + low rating) keep the first; `add_postmortem` ignores a duplicate.

## 3. Interfaces

- Action `write_postmortem` (`zebra_tasks/agent/postmortem.py`): properties `trigger`, `run_id`
  (default process `run_id`), `goal`, `workflow_name`, `success` (failure trigger skips on
  success), `error`, `rating`, `user_feedback`, `model` (low), `output_key` (`postmortem`).
  Reads `__task_executions__` for the steps. Output `{written, lesson, root_cause, ...}` or
  `{written: false, reason}`. Never fails; no LLM or no lesson → nothing stored.
- `with_lessons(goal, props)`: appends `<lessons>` (from `memory_shortlist.lessons_context`) to the
  child goal in `execute_goal_workflow`.
- `consult_memory` output gains `lessons_context` (also in `memory_context`).
- Workflows: `agent_main_loop.yaml` v17 (`assess_and_record → write_postmortem →
  update_conceptual_memory`); new system workflow `postmortem.yaml` (*Postmortem*).
- `zebra_agent/postmortem.py`: `needs_failure_postmortem`, `start_postmortem`,
  `postmortem_failed_goal`, `LOW_RATING_MAX = 2`.
- Web: `GET /journal/` (`postmortem_journal`, nav "Journal").

## 4. Control flow

```
failed goal run: … → assess_and_record → write_postmortem (low tier) → update_conceptual_memory → …
timeout/crash:   daemon reconcile / AgentLoop FAILED → needs_failure_postmortem?
                   (Agent Main Loop, FAILED, no __task_output_write_postmortem, not kill switch)
                 → Postmortem process (inline) → write_postmortem(trigger=timeout)
low rating:      record_rating(≤2) → background task → Postmortem(trigger=low_rating, feedback)
next goal:       consult_memory → search_postmortems(goal) → memory_context + <lessons> in child goal
```

## 5. Configuration

None. `LESSONS_LIMIT = 3` (consult_memory), `LOW_RATING_MAX = 2`. Oracle vector search follows
`MEMORY_VECTOR_SEARCH` / `MEMORY_VECTOR_MAX_DISTANCE` (#169).

## 6. Open questions / risks

- Recalled lessons are untrusted text (failure output, user feedback): `with_lessons` strips `<lessons>` tags and labels them notes, not instructions; each is capped at 400 chars, 3 per goal. The journal relies on Django autoescaping.
- Lessons can be wrong; they are advisory context and visible in the journal, but there is no
  delete/curate action yet (a Dream Cycle review could prune them).
- The low-rating postmortem runs as a background task in the web process; a restart before it
  finishes loses it.
- A failure before `execute_workflow` (e.g. a gate's LLM error) gets a `timeout` postmortem; the
  label is "timed out or crashed".

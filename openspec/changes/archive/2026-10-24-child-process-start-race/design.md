## Context

Evidence from prod (#227), read-only queries on 2026-10-24:

- Child `7941d516` of goal `a1435839`: `process_started` at 20:19:38.394 and .406, two `count`
  tasks, `parent_process_id` column empty although `__parent_process_id__` is set. The first
  `count` completed at 20:19:38.55; the second ran only at 20:40:33.
- `ProcessLockModel` locks are 30 s with `select_for_update(nowait=True)`; the loser's
  `start_process` → `transition_task` raised `LockError`.
- Children with the lost link: `9df1f16b`, `4b264140` (19 Oct, failed), `7941d516`.
- 43 RUNNING processes; recovery fails several each restart with `Definition … not found`.

## Decisions

- **Link at creation, not after.** `WorkflowEngine.create_process` already takes
  `parent_process_id` / `parent_task_id` (used by `llm_agent` and the gym). The three remaining
  spawners switch to it. This closes the window rather than narrowing it, and also stops the
  daemon's later full-row save from wiping the link.
- **No CAS in `start_process`.** It would need a new conditional-update method on every store
  (memory, SQLite, Postgres, Django). With no second starter left it is not needed today.
- **Missing definition → `fail_process`.** `fail_process` does not load the definition, so it
  works for these runs; it also fails live children, which cannot resume either. Only
  `DefinitionNotFoundError` is caught: other recovery errors stay logged-and-skipped as before.

## Risks

- Failing old RUNNING processes on the first restart after deploy marks their runs failed on the
  activity page. They are already dead (no definition), so this makes the UI honest.

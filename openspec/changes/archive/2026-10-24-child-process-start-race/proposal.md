## Why

Master pipeline 2982845649 failed smoke (#227): the "Count from 1 to 100" goal never finished.
The step journal shows why. The goal's child process `7941d516` has **two** `process_started`
events 12 ms apart, so it was started twice:

1. `execute_goal_workflow` created the child with `create_process()` (saved with no parent), then
   set `parent_process_id` and saved it again, then started it.
2. In that gap the daemon's queue (`GoalScheduler`, top-level CREATED processes only) saw a
   CREATED process with no parent, took it for a queued goal and started it too. Its
   `start_process` saved the row it had loaded, wiping the parent link.

Each start created a `count` task. One ran; the other hit `LockError` and stayed active, so the
child (and the smoke goal) hung until something re-ran it 21 minutes later. Prod has two more
children with the lost link (19 Oct, both failed). `subworkflow` and `parallel_subworkflows`
have the same create-then-link pattern; `llm_agent` and the gym already link at creation.

The same daemon log showed recovery failing with `DefinitionNotFoundError` for runs whose
definition no longer exists. Prod has 43 RUNNING processes, some from July, retried and logged as
errors on every restart. They can never resume.

Closes #227.

## What Changes

- `execute_goal_workflow`, `subworkflow` and `parallel_subworkflows` pass `parent_process_id` /
  `parent_task_id` to `create_process`, so a child is never saved without its parent and the
  daemon cannot pick it.
- Startup recovery fails a RUNNING process whose definition cannot be found, with an `__error__`
  saying so, instead of logging and retrying it on every restart.

## Non-goals

- An atomic CREATED→RUNNING compare-and-set in every store. Linking at creation removes the only
  known second starter; revisit if another appears.
- Repairing the three prod children whose link was lost: all are terminal.
- Keeping old definition versions (#219, already shipped for built-ins).

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A goal's child process is never visible to the daemon queue as a top-level goal | Unit tests: for `execute_goal_workflow`, `subworkflow` and `parallel_subworkflows`, the child's first save already carries `parent_process_id` / `parent_task_id`, and the queue's query (CREATED, `exclude_children`), run after every save, never returns it. The tests fail on the old code |
| O2 | A child process is started exactly once | Unit test: each child has one `process_started` journal event. On prod, no child created after the deploy has two `process_started` events or a `__parent_process_id__` property with an empty `parent_process_id` column |
| O3 | Recovery stops retrying runs whose definition is gone, and only those | Unit tests: a missing definition fails the process with an `__error__` naming it, others still recover; a store error loading the definition leaves the process RUNNING with no `__error__`. On prod, after the deploy's restart the daemon log has no `Failed to recover … not found` lines and those processes are FAILED |

Zebra's outcome feedback (advisory): O1 tightened to "first save carries the link"; O3 pinned to
the missing-definition case with a transient-error test; O4 (smoke passes once) dropped, since one
green run cannot show an intermittent race is fixed. Not taken: a concurrent second-start test
(the second starter is removed; a compare-and-set is a non-goal) and unsticking old processes
(all three affected children are already terminal).

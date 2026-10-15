## Context

A continuation's `previous_run_context` reaches the child workflow only as goal text. Human
forms don't read the goal, and forms generated at runtime (`schema: "{{followup_form}}"`) depend
on earlier LLM outputs, so replaying answers into a fresh run cannot work. The failed child
already holds the complete workflow state; its unfinished tasks remain as FAILED task instances
(`fail_process` marks every live task FAILED, completed ones are deleted).

## Decisions

- **Resume, don't replay.** Copy the failed child's state into a new child and start at its
  unfinished tasks. Keeping a new process (not reviving the FAILED one) respects the process state
  machine and keeps each run's cost and journal separate.
- **What is carried:** properties not starting with `__`, plus `__task_output_*`. Engine
  bookkeeping (`__error__`, cost/token totals, parent links, user identity) is set fresh.
- **When:** only `continuation_decision == same_workflow`, previous run `success` false, same
  workflow name, every unfinished task id still in the current definition. Anything else starts
  from the beginning, as before.
- **Finding the failed child:** top-level FAILED (then COMPLETE) processes with
  `run_id == previous_run_context.run_id`; newest FAILED child whose definition name matches.
- **Crash safety:** `__resumed_from__.task_ids` on the child lets the F129 re-attach path start a
  CREATED child at the same tasks.

## Risks / Trade-offs

- A user who wants a clean start after a failure gets a resume when the assessor picks
  `same_workflow`; they can start a new goal instead. Not adding a choice until it's asked for.
- Task executions recorded for the new run include carried-over outputs, so the run's history
  shows the full workflow, not just the retried steps.

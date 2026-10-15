## Context

`execute_workflow` runs with `continue_on_failure: true`, so a failed goal run arrives as
`execution_result.success == false` and flows through assess/learn to `report_outcome`, which
fails the process (#140). Human tasks (`auto: false`) already park a goal cleanly: the daemon hands
it off (#141), the CLI reports "Awaiting human input", and #185 means no goal timeout runs while a
human answers.

## Decisions

- **Hook in the main loop, not the engine.** Detection is "the goal workflow failed", which covers
  task errors, retries running out inside the child and the goal timeout (#142): all surface as a
  failed child. An engine-level hook would have to invent tasks that aren't in the definition.
- **Loop back to `execute_workflow`.** Routing creates a fresh task instance with no
  `__child_process_id__`, so a retry spawns a new child instead of re-attaching (F129) to the
  failed one.
- **Guidance is appended, the goal is kept.** `__help_history__` (list of
  `{error, decision, guidance}`) is appended to the child's goal by `with_help_guidance`, like
  `with_previous_run`. `goal` stays as the user typed it for run records and memory. Redirect is
  the exception: the user changed what they want, so `goal` becomes the new text (the original is
  kept as `original_goal`) and is re-checked by the ethics input gate.
- **Bounded.** `__help_requests__` counts requests; past `max_help_requests` (default 2) the
  failure proceeds as before, so a goal can't loop on a human forever.
- **Abandon keeps #140.** The error gets "(abandoned after asking for help)" and flows through
  assess/learn to `report_outcome`, ending FAILED.
- **Help request text.** Haiku with the goal, workflow, error and the child's task progress
  (`__task_executions__`); JSON `{tried, stuck_on, need, voice, confidence}`. Rendered into
  `help_request_display` for the read-only form field. Provider or parse failure degrades to a
  plain request built from the error; the step never fails the goal.

## Risks / Trade-offs

- Goals queued by routines with nobody watching now park instead of failing. They show in the
  pending-task UI like an ethics dilemma; the budget caps how often.
- A help request nobody answers waits indefinitely, like an ethics-dilemma form. It is visible in
  the pending-task UI; no expiry is added here.
- Retry guidance goes into the child goal without another ethics gate. It comes from the goal's
  own user, like answers to human tasks inside the child; redirect (a new goal) is re-gated.
- Only "the goal workflow failed" is detected. Low confidence and no-progress loops (from the
  issue's scope) are deferred: they need a progress signal the engine doesn't have yet.
- `execution_result` and `assess_and_record` reflect the last attempt; the earlier failed
  children's cost is still on the process via child cost propagation.

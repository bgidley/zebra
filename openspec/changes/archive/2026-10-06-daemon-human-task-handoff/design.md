## Context

`WorkflowEngine.start_process()` runs every auto task inline and only returns when the process completes or no auto work remains (i.e. it is parked on a human task). The daemon's post-start poll therefore only ever covered human-task pauses. A human task in the *child* workflow is worse: `execute_goal_workflow` polls the child inside the parent's inline chain, so `start_process` itself never returns until the human answers.

## Decisions

- **Background execution, bounded wait in the tick.** `_tick` wraps `engine.start_process` in `asyncio.create_task` and polls: done → reconcile and return; human task pending anywhere in the process tree → log `[daemon:await]` and return, leaving the goal tracked. This keeps the existing contract that an auto-only goal is finished when `_tick` returns (e2e budget test) while unblocking the queue on human pauses, including the child-workflow case.
- **Serial pacing preserved.** A tracked goal whose task is still running and not awaiting a human blocks pickup. This happens once a human answers a child-workflow task and execution resumes in the daemon. Goals without a live task (main-loop human task completed through the web, which drives the rest inline in the web request; or seeded after restart) never block pickup; they are only reconciled.
- **In-memory tracker, seeded from the store.** No new table. Daemon-started goals carry `__daemon_started__: true`; on the first tick after start the tracker adds RUNNING top-level processes with that marker. Reconciliation is idempotent per tracker (a goal is dropped once logged).
- **Kill switch.** For tracked goals with a live task that is not awaiting a human: cancel the task, await it, then `fail_process(..., "Kill switch activated")`. Goals parked on a human task are left alone (they consume nothing; the operator can still fail them).
- **`process_goal()`**: after `start_process`, check `find_pending_human_task` each poll; if found, return `AgentResult(success=False, awaiting_input=True, error="Awaiting human input: <task name>")`.

## Risks / Trade-offs

- Once a human answers, two goals may execute at once (the resumed one plus a newly picked one). This is acceptable; budget is still checked before each pickup.
- A goal stuck RUNNING with no live task and no human task (e.g. flagged for manual review) is reconciled only when it eventually terminates; it no longer blocks the queue.
- No execution time bound yet — #142.

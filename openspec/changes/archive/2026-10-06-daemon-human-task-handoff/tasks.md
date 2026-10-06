## 1. Human-task detection

- [x] 1.1 Add `find_pending_human_task(engine, process_id)` (process + RUNNING descendants, READY `auto: false`)
- [x] 1.2 Unit tests (main-process task, child-process task, none)

## 2. Goal tracker and daemon

- [x] 2.1 Add `GoalTracker` (track, seed from store, reconcile terminal goals, `has_active_goal`, `cancel_active`)
- [x] 2.2 Rework daemon `_tick`: kill switch cancels active goals; reconcile; skip pickup while a goal is active; background `start_process`; wait until done or awaiting human; mark `__daemon_started__`
- [x] 2.3 Wire one tracker per `run_daemon_loop`; update metrics label docs
- [x] 2.4 Tests: dilemma hand-off then next goal picked; child human task hand-off; reconciliation logs once; restart seeding; kill switch cancel; existing kill-switch/budget tests still pass

## 3. process_goal

- [x] 3.1 `AgentResult.awaiting_input`; `process_goal` returns it when parked on a human task
- [x] 3.2 Test via ethics escalation

## 4. Docs

- [x] 4.1 Update `specs/zebra-as-is.md` daemon section

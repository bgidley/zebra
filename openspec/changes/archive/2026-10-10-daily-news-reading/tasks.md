# Tasks

Branch: `f155/daily-news-reading`. Commits reference #155.

## 1. Scheduler

- [x] 1.1 `Routine` gains `goal`, `goal_priority`, `run_as`; YAML loader parses them
- [x] 1.2 `SchedulerLoop` dispatches goal routines via `queue_goal_fn`, skipping when one is pending
- [x] 1.3 Tests in `zebra-agent/tests/`

## 2. Goal plumbing

- [x] 2.1 `queue_goal(extra_properties=...)`; daemon wires `queue_goal_fn` with owner resolution
- [x] 2.2 `workflow_selector` honours `requested_workflow`
- [x] 2.3 Tests

## 3. Kagi News

- [x] 3.1 `kagi_news_fetch` and `kagi_news_read` actions + entry points
- [x] 3.2 Tests with mocked HTTP

## 4. Knowledge

- [x] 4.1 `world` category + decay half-life + Django migration
- [x] 4.2 `store_learned_knowledge` `update_agent_entries`
- [x] 4.3 Tests

## 5. Workflow and routine

- [x] 5.1 `daily_news_reading.yaml` workflow
- [x] 5.2 `fixtures/routines/daily_news_reading.yaml`
- [x] 5.3 Workflow test with stubbed actions

## 6. Docs

- [x] 6.1 Update `specs/zebra-as-is.md` and package AGENTS.md files

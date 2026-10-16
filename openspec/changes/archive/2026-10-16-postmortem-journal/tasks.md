## 1. Memory

- [x] 1.1 `PostmortemEntry` dataclass; `MemoryStore` add / recent / by-run-id / search (keyword default)
- [x] 1.2 In-memory backend
- [x] 1.3 `PostmortemModel` + migration, `DjangoMemoryStore`, embeddings table

## 2. Actions & workflows

- [x] 2.1 `write_postmortem` action (haiku, voice, dedup, never fails) + entry point
- [x] 2.2 `agent_main_loop.yaml` v17: `write_postmortem` after `assess_and_record`
- [x] 2.3 `postmortem.yaml` system workflow
- [x] 2.4 `consult_memory` lessons + `with_lessons` in `execute_goal_workflow`

## 3. Triggers

- [x] 3.1 `zebra_agent/postmortem.py`: `start_postmortem`, `needs_failure_postmortem`
- [x] 3.2 Daemon reconcile hook + `AgentLoop` failed-run hook
- [x] 3.3 `AgentLoop.record_rating` low-rating trigger

## 4. UI

- [x] 4.1 `/journal/` page + nav item

## 5. Tests & docs

- [x] 5.1 Unit tests: store, action, consult_memory, with_lessons, triggers, main loop, journal view
- [x] 5.2 `specs/zebra-as-is.md`, `specs/postmortem-journal-design.md`, AGENTS.md files

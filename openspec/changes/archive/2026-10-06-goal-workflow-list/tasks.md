## 1. Shared builder

- [x] 1.1 Add `list_goal_workflows(library)` to `zebra_agent/library.py`
- [x] 1.2 Use it in `AgentLoop.process_goal`; remove `_is_system_workflow`
- [x] 1.3 Use it in `api/goals.queue_goal`; take provider from `LLM_PROVIDER`
- [x] 1.4 Use it in the `queue_goal` task action

## 2. Selector

- [x] 2.1 Refresh candidates from `__workflow_library__` with fallback to the property
- [x] 2.2 Render "N/A" success for `use_count` 0

## 3. Cleanups

- [x] 3.1 Remove stale "memory compaction" docstrings in `loop.py`
- [x] 3.2 Drop `synchronized: true` from `flag_concerns` in `agent_main_loop.yaml`

## 4. Tests and docs

- [x] 4.1 Tests: builder filter/shape, direct path excludes system-tagged workflows, selector refresh + fallback, N/A rendering, provider setting
- [x] 4.2 Update `specs/zebra-as-is.md`

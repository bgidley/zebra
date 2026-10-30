## 1. Launch choke point

- [x] 1.1 `zebra_tasks/launch.py`: `LaunchRefused`, `check_launch` (no-op), `create_library_process`
- [x] 1.2 Route `execute_goal_workflow`, `subworkflow`, `parallel_subworkflows`, `llm_agent` tools through it, handling refusal
- [x] 1.3 Route `AgentLoop` (goal + dream cycle), `run_named_workflow`, scheduler routines through it
- [x] 1.4 Tests: refusal stops every entry point; source scan with allowlist

## 2. Reversibility hints

- [x] 2.1 Set `reversibility_hint` on every unhinted action (zebra-tasks + zebra-py `shell`)
- [x] 2.2 Test: every registered action declares its hint; writers are not `always_reversible`

## 3. Strict gym mode

- [x] 3.1 `unsafe_reason(..., strict=False)`; strict refuses non-`always_reversible`
- [x] 3.2 Tests: `file_delete` passes gate, fails strict; pure workflow passes strict

## 4. Protected workflows

- [x] 4.1 Rename `curator._is_protected` to `is_protected_workflow`
- [x] 4.2 `zebra_agent/commons.py` `commons_exportable()` + tests

## 5. Docs

- [x] 5.1 `specs/zebra-as-is.md`, `specs/zebra-commons-design.md`, package `AGENTS.md`

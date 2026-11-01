## ADDED Requirements

### Requirement: One launch choke point for library workflows
Every start of a workflow loaded from the workflow library by a goal, the agent loop, a direct
run, a scheduled routine, `subworkflow`, `parallel_subworkflows` or an `llm_agent` tool call SHALL
create its process through `zebra_tasks.launch.create_library_process`, which SHALL call
`check_launch` before creating the process. `check_launch` SHALL allow every launch until a later
change extends it. When it raises `LaunchRefused`, no process SHALL be created and the entry point
SHALL report the refusal instead of starting the workflow.

#### Scenario: Refusing stops every entry point
- **WHEN** `check_launch` is patched to raise `LaunchRefused`
- **THEN** a goal's `execute_goal_workflow`, the agent loop, `run_named_workflow`, a scheduled
  routine, `subworkflow`, `parallel_subworkflows` and an `llm_agent` tool call each create no
  child process and report the refusal

#### Scenario: No call bypasses the choke point unnoticed
- **WHEN** production code calls `create_process(` outside `zebra_tasks/launch.py`
- **THEN** the source-scan test fails unless the call is on its allowlist with a reason

#### Scenario: The hook is a no-op today
- **WHEN** any entry point starts a library workflow with the default `check_launch`
- **THEN** the workflow starts exactly as before

### Requirement: Every action declares its reversibility hint
Every action registered through the `zebra.tasks` entry points or zebra-py's default actions SHALL
set `reversibility_hint` on its own class. An action SHALL be `always_reversible` only if its
effects stay within the running process (reads, LLM calls, pure transforms, gates, audit
appends). Actions that write files, stores, the workflow library or the goal queue, run code, or
start child workflows SHALL NOT be `always_reversible`.

#### Scenario: No inherited default
- **WHEN** the hint test loads every registered action class
- **THEN** each defines `reversibility_hint` itself

#### Scenario: Writers are not reversible
- **WHEN** the hints of `file_write`, `file_copy`, `file_move`, `file_delete`, `python_exec`,
  `subworkflow`, `parallel_subworkflows`, `queue_goal`, `add_knowledge`,
  `store_learned_knowledge`, `save_values_profile`, `update_conceptual_memory` and
  `propose_trust_promotion` are read
- **THEN** none is `always_reversible`

### Requirement: Strict gym mode
`unsafe_reason(definition, registry, *, strict=False)` SHALL keep its current rules when `strict`
is false. With `strict=True` it SHALL additionally refuse any task whose action is not
`always_reversible`, naming the action and its hint.

#### Scenario: file_delete in gate and strict mode
- **WHEN** a workflow with only auto tasks uses `file_delete`
- **THEN** `unsafe_reason(definition, registry)` returns None, and
  `unsafe_reason(definition, registry, strict=True)` returns a reason naming `file_delete`

#### Scenario: Pure workflow passes strict mode
- **WHEN** a workflow uses only `always_reversible` actions
- **THEN** `unsafe_reason(definition, registry, strict=True)` returns None

### Requirement: Protected workflows never leave the deployment
`zebra_agent.commons.commons_exportable(workflow)` SHALL return false for any workflow tagged
`system` or named in `SYSTEM_WORKFLOW_NAMES`, and true otherwise. Later Commons code SHALL call it
before offering, exporting or syncing a workflow.

#### Scenario: Agent Main Loop stays home
- **WHEN** `commons_exportable` is called with the library's *Agent Main Loop*
- **THEN** it returns false

#### Scenario: Ordinary workflow is exportable
- **WHEN** it is called with a goal workflow that has no `system` tag and a non-system name
- **THEN** it returns true

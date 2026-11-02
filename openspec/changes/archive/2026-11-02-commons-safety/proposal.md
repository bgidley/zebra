## Why

The Zebra Commons (epic #41, `specs/zebra-commons-design.md`) will let Zebra adopt workflows other
Zebras wrote. Before any of that code exists, three safety holes need closing (#245, S0):

- Library workflows start from seven places (goals, the agent loop, direct runs, scheduled
  routines, `subworkflow`, `parallel_subworkflows`, `llm_agent` tools), so a pre-run check such as
  S3's "supervised" approval would have to be copied into each and could be missed.
- Most actions carry no `reversibility_hint`, so they default to `context_dependent`, and the
  golden gym only refuses `always_irreversible`. A workflow using `file_delete`, `python_exec` or
  `queue_goal` runs in the gym before any human has seen it.
- Nothing says Zebra's own system workflows (the main loop, the dream cycle) must never leave the
  deployment.

## What Changes

- New `zebra_tasks/launch.py`: `create_library_process()` is the one choke point every start of a
  library workflow uses; it calls `check_launch()`, a no-op hook today (S3 plugs the supervised
  approval into it) that may raise `LaunchRefused`. All seven entry points use it and handle a
  refusal without starting anything. A test scans the source so no new `create_process` call can
  bypass it unnoticed.
- Every registered action declares its `reversibility_hint` on its own class. Read-only and
  pure-LLM actions become `always_reversible`; actions that write files, stores, the library, the
  goal queue or start child workflows are explicitly `context_dependent`. A test fails if an
  action relies on the inherited default.
- `unsafe_reason(definition, registry, *, strict=False)`: with `strict=True` only
  `always_reversible` actions pass (import mode, S3). The default gate mode is unchanged.
- `zebra_agent.commons.commons_exportable(workflow)`: false for protected workflows (`system` tag
  or `SYSTEM_WORKFLOW_NAMES`). `curator._is_protected` becomes the public `is_protected_workflow`.

## Capabilities

### New Capabilities
- `commons-safety`: launch choke point, explicit reversibility hints, strict gym mode, protected
  workflows never exported.

### Modified Capabilities
<!-- None: golden-task-gym's gate mode is unchanged. -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every start of a library workflow goes through one choke point, and refusing there starts nothing | `test_launch.py`: patching `check_launch` to refuse stops the goal (`execute_goal_workflow`), agent loop, direct run, scheduled routine, `subworkflow`, `parallel_subworkflows` and `llm_agent` tool paths, with no child process created; a source scan fails on any `create_process` call outside the choke point that is not on a reasoned allowlist |
| O2 | No action relies on the default reversibility hint, and each hint is honest | A test over all `zebra.tasks` entry points and zebra-py defaults fails if an action class does not set `reversibility_hint` itself; file writers, `python_exec`, `subworkflow`, `queue_goal` and memory / knowledge / values / trust writers are not `always_reversible` |
| O3 | Strict gym mode runs only `always_reversible` actions, and today's gate mode is unchanged | Tests: a workflow with `file_delete` passes `unsafe_reason(...)` but `strict=True` rejects it with a reason naming the action; parameterised over every registered action, strict passes exactly the `always_reversible` ones; the existing gym tests pass unchanged |
| O4 | Zebra's protected workflows are never exportable | Tests: `commons_exportable` is false for *Agent Main Loop*, *Dream Cycle* and any `system`-tagged workflow, true for an ordinary goal workflow |

## Non-goals

- An export API: none exists yet; S2/S3b/S4 call `commons_exportable` (Zebra feedback asked for
  an end-to-end export test, which lands with S2).

- Commons models, Nostr, the supervised approval itself (S3, #230), `foreign_users` (S2a).
- Changing the gym's default gate rule or the trust gate.

## Impact

- `zebra-tasks`: new `launch.py`; `execute_workflow.py`, `subtasks/spawn.py`, `subtasks/parallel.py`,
  `llm/agent.py` use it; `gym.py` strict mode; `curator.py` rename; hints on ~35 actions.
- `zebra-py`: `shell` declares its hint.
- `zebra-agent`: `loop.py`, `direct_run.py`, `scheduler/loop.py` use the choke point; new
  `commons.py`.
- Docs: `specs/zebra-as-is.md`, `specs/zebra-commons-design.md`, package `AGENTS.md`.
- Requirements: REQ-NET-005, REQ-TRUST-002. Refs #245, #41.

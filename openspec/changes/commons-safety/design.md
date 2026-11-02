## Context

S0 of the Zebra Commons (#245). See `specs/zebra-commons-design.md` (supervised use, gym import
mode, "never leaves the deployment").

## Decisions

### The choke point lives in zebra-tasks
`subworkflow`, `parallel_subworkflows`, `llm_agent` and `execute_goal_workflow` are in
`zebra-tasks`, which cannot import `zebra-agent`. So `zebra_tasks/launch.py` holds:

```python
async def check_launch(definition, *, entry, properties) -> None   # no-op hook; raise LaunchRefused
async def create_library_process(engine, definition, *, entry, properties=None,
                                 parent_process_id=None, parent_task_id=None) -> ProcessInstance
```

It guards **creation**, not start: callers start the child differently (inline with timeout,
suspended on, background). Refusing before `create_process` means no process exists to clean up.
`entry` names the path (`goal`, `agent_loop`, `dream_cycle`, `direct_run`, `routine`,
`subworkflow`, `parallel_subworkflows`, `llm_agent_tool`) so S3 can treat them differently.
`create_library_process` looks `check_launch` up as a module global, so one patch covers all.

A refusal at each entry point:
- `execute_goal_workflow`, `subworkflow`: the task fails with the reason.
- `parallel_subworkflows`: the refused child is recorded as a failed result under its key; with
  `fail_fast` no more children start.
- `llm_agent`: an error tool result, as for an unknown tool.
- `direct_run`: `DirectRunError`. Scheduler: logged skip, status `refused`. Agent loop goal and
  dream cycle: the exception propagates to the caller, as other start failures do.

### Other `create_process` calls stay, on an allowlist
Some calls start a *named built-in* workflow from trusted code (Postmortem, Bug Report, Values
Profile Wizard, Resolve Knowledge Contradiction, Zebra Improvement Request, the queued Agent Main
Loop) or run the gym's own sandboxed copies. S3 only needs the choke point where the workflow can
be one the library adopted. A test scans `zebra-*/` production code for `create_process(` and
fails on any call outside `launch.py` not in an allowlist with its reason, so a new entry point
must decide.

The gym is allowlisted: it runs candidates under `unsafe_reason`, and S3 import mode uses strict
mode there instead of the supervised hook (the gym *is* the pre-approval judge).

### Hints: "always_reversible" means no effect outside the run
`always_reversible` is set only for actions whose effects stay in the process's own properties:
reads, LLM calls, pure transforms, waiting on a child, gates and audit appends (precedent:
`record_ethics_review`). Anything that writes a file, a store (memory, knowledge, metrics, values,
trust suggestions), the workflow library or the goal queue, or starts child workflows, or runs
code, is explicitly `context_dependent` — the trust gate keeps judging it at runtime and strict
mode refuses it. No hint moves to `always_irreversible`, so the gym's gate mode and the trust gate
behave as before for those actions (`file_delete` still passes the gate, per the issue).

### Strict mode
`unsafe_reason(definition, registry, *, strict=False)`. Strict adds one rule after the existing
ones: any action whose hint is not `always_reversible` is refused with
`action 'X' is not always reversible (context_dependent)`. Gate mode callers are unchanged.

### commons_exportable
`zebra_agent/commons.py`: `commons_exportable(workflow) -> bool` returns
`not is_protected_workflow(workflow)` for anything with `name` and `tags` (a `WorkflowInfo`). S2a
adds `foreign_users`. `curator._is_protected` is renamed to the public `is_protected_workflow`.

## Risks / open questions

- Existing `always_reversible` hints that wrote outside the run moved to `context_dependent`
  (review finding): `workflow_curator` (retires library workflows), `review_knowledge` (rewrites
  the knowledge store, starts processes), `propose_zebra_improvements` (starts processes),
  `write_postmortem` (memory store). Only dream-cycle / system workflows use them, and those have
  no trust gate, so runtime behaviour is unchanged. A source-scan test now fails if any
  `always_reversible` action's module makes a store / library / process-start call, unless it is
  allowlisted with a reason (`REVERSIBLE_WRITERS`): the ethics audit appends (`ethics_gate`,
  `record_dilemma_resolution`, `record_ethics_review`) and `claude_code_build` (stages an
  unpublished build job; its wait is a non-auto task the gym refuses). The `git_*` actions write
  only inside the sandboxed workspace and stay reversible. S3 may still refuse
  `claude_code_build` by name in import mode.
- `check_launch` has no access to the human-task machinery yet; S3 decides how a refusal becomes
  a pending approval rather than a failure.

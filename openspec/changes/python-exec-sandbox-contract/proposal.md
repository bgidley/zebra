## Why

Workflows disagree about what `python_exec` allows (#323, raised by the dream cycle). The built-in
*Compute* prompt lists a few modules by hand, a *Compute with Repair* planner prompt forbids all
imports, and *Outcome Spec Review* (`note_cancellation`, `log_run`) uses `import json`. The real
contract lives only in `PythonExecAction` (`ALLOWED_MODULES`, `BLOCKED_BUILTINS`, the `result`
variable), so any prompt or edit is a guess and at least one workflow fails at run time with
`ImportError: Module 'x' is not allowed`.

## What Changes

- New `zebra_tasks/compute/sandbox.py`: the one definition of the `python_exec` contract
  (allowed modules, blocked builtins, pre-imported names, `props` / `result` / stdout contract,
  no file or network access), plus `describe_contract()` (prompt text) and
  `check_code(code)` (static AST check returning findings for disallowed imports and blocked
  builtin calls).
- `PythonExecAction` reads its allowed modules, blocked builtins and pre-imports from that module;
  nothing is duplicated. Its docstring and `description` point at it.
- The contract text is exposed to prompts as the runtime template root `{{python_sandbox}}`
  (resolved by `ExecutionContext.resolve_template`, listed with the other runtime roots in
  `validate_contracts`). Built-in workflows that describe the sandbox by hand (*Compute*) use it.
- `WorkflowLibrary.save()` validates every `python_exec` task whose `code` is a literal (no
  `{{...}}`): a disallowed import or blocked builtin raises `WorkflowContractError` naming the task
  and module. Code that is generated at run time (`code: "{{code}}"`) is still checked when it runs,
  and its failure message quotes the contract.

## Capabilities

### New Capabilities
- `python-exec-sandbox`: single contract for `python_exec`, exposed to prompts, enforced at save time.

### Modified Capabilities
<!-- None: workflow contract checks (#271) gain a rule but their requirements are unchanged. -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The sandbox contract is defined once and `python_exec` runs by it | `test_python_exec_sandbox.py`: `PythonExecAction` has no module or builtin list of its own; every module in the contract imports, every other module fails with `ImportError`, every blocked builtin is absent; a source scan finds no second hand-written module list in `zebra-agent/workflows/*.yaml` |
| O2 | Prompts get the real contract | `{{python_sandbox}}` resolves to text naming each allowed module and the `result` rule; the built-in *Compute* planner prompt uses it, and a test fails if its text and `ALLOWED_MODULES` diverge |
| O3 | A workflow whose literal `python_exec` code breaks the contract cannot be saved | `WorkflowLibrary.save()` of a workflow with `import os` (or `open(...)`) raises `WorkflowContractError` naming the task and `os`; the same workflow with `import json` saves; templated `code: "{{code}}"` is not rejected |
| O4 | Every shipped workflow already honours it | A test loads all `zebra-agent/workflows/*.yaml` and `zebra-py` templates and finds no sandbox findings |
| O5 | A runtime failure tells the author what is allowed | A run of disallowed code fails with the import error followed by the contract text, visible in the task's failure message |

## Non-goals

- Making `python_exec` a real sandbox (it stays in-process with light restrictions; real code goes
  through the host builder, #98).
- Rewriting *Compute with Repair* / *Outcome Spec Review*: they are library (dream-written)
  workflows, not shipped files here. They are covered when next saved, and a follow-up request can
  align their prompts using `{{python_sandbox}}`.
- Per-deployment configuration of the allowed list.

## Impact

- `zebra-tasks`: `compute/sandbox.py` (new), `compute/python_exec.py`.
- `zebra-py`: `ExecutionContext.resolve_template` and `definitions/contracts.py` know the
  `python_sandbox` root (value supplied by the engine's extras, see design).
- `zebra-agent`: `library.py` `_check_contracts`; `workflows/compute.yaml` (version bump).
- Docs: `specs/zebra-as-is.md`, `zebra-tasks/README.md`.

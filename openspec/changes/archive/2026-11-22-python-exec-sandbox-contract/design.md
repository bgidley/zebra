## Context

Issue #323. `python_exec` (`zebra-tasks/zebra_tasks/compute/python_exec.py`) enforces its limits
with `ALLOWED_MODULES`, `BLOCKED_BUILTINS` and a restricted `__import__`. Workflow authors (humans
and LLMs) never see them. #271 already validates `{{...}}` references on `WorkflowLibrary.save()`
through `_check_contracts`, which is the natural place for one more rule.

## Decisions

### One module owns the contract
`zebra_tasks/compute/sandbox.py` holds `ALLOWED_MODULES`, `BLOCKED_BUILTINS`, `PRELOADED`
(`math json datetime re random`), `describe_contract()` and `check_code(code) -> list[str]`.
`PythonExecAction.ALLOWED_MODULES` / `BLOCKED_BUILTINS` stay as aliases of the module constants so
existing tests and callers keep working.

`check_code` parses with `ast` and reports: `import x` / `from x import y` whose top-level package
is not allowed, calls of blocked builtins by name (`open`, `eval`, `exec`, `compile`, `input`,
`__import__`, `breakpoint`), and a syntax error (left to the runtime for the message, so the
check ignores it). It is best-effort static analysis (dynamic `getattr` tricks are out of scope:
the runtime restricted `__import__` remains the real enforcement).

### Exposure to prompts: `{{python_sandbox}}`
`describe_contract()` returns a short fixed text. It is exposed as a runtime root rather than a
process property so it never lands in persisted properties and cannot drift from the code:
`ExecutionContext.resolve_template` falls back to `extras["__python_sandbox__"]` for the root
`python_sandbox`; `IoCActionRegistry`/container start-up (and `AgentLoop`, like the other
`__...__` extras) set that extra from `describe_contract()`. `validate_contracts` adds
`python_sandbox` to `_RUNTIME_ROOTS`, so a reference is not flagged as unknown. zebra-py does not
import zebra-tasks: it only reads the extra.

### Save-time enforcement
`_check_contracts` (library.py) also walks task definitions with `action: python_exec`. A
`code` property with no `{{` is passed to `check_code`; each finding becomes an error naming
task id and symbol, raised as the existing `WorkflowContractError`. `zebra_tasks` is imported
lazily as `_check_leaks` already does; if unavailable the rule is skipped with a warning.
Templated code cannot be checked statically: it is validated when it runs.

### Runtime message
On `ImportError` from the sandbox import hook (and blocked-builtin `NameError`), the failure message
appends `describe_contract()`, so a repair loop (*Compute with Repair*) gets the real rules in the
error it feeds back.

## Risks / open questions

- A workflow already in a user's library that breaks the contract keeps loading; it is only
  rejected on its next save. The shipped-workflows test (O4) covers built-ins only. A library audit
  (dream-cycle curator) is deferred.
- Static check false negatives (indirect imports) rely on runtime enforcement.
- The `extras` hook for the prompt text needs to be set in every engine construction path
  (`AgentLoop`, web, CLI); implementation adds a test over the container wiring.

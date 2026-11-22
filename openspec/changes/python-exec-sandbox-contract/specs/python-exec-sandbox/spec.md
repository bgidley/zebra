## ADDED Requirements

### Requirement: One definition of the python_exec contract
The allowed modules, blocked builtins, pre-imported names and result rules of `python_exec` SHALL be
defined once in `zebra_tasks.compute.sandbox`, and `PythonExecAction` SHALL enforce exactly that
definition.

#### Scenario: Allowed and disallowed imports
- **WHEN** code imports a module in the contract and another code imports one outside it
- **THEN** the first runs and the second fails with `ImportError` naming the module

#### Scenario: No second list
- **WHEN** the shipped workflow YAML and `PythonExecAction` are scanned for hand-written module lists
- **THEN** none is found outside `sandbox.py`

### Requirement: The contract is available to prompts
The template `{{python_sandbox}}` SHALL resolve to text describing the allowed modules, blocked
builtins and the `result` / `props` rules, and `validate_contracts` SHALL accept it as a runtime root.

#### Scenario: Compute planner prompt
- **WHEN** the built-in *Compute* workflow renders its planner prompt
- **THEN** the text lists every module in `ALLOWED_MODULES`

### Requirement: Saving validates python_exec code against the contract
`WorkflowLibrary.save()` SHALL raise `WorkflowContractError` for a `python_exec` task whose literal
`code` imports a disallowed module or calls a blocked builtin, naming the task and symbol. Code
containing `{{...}}` SHALL NOT be rejected at save time.

#### Scenario: Disallowed import refused
- **WHEN** a workflow with a `python_exec` task containing `import os` is saved
- **THEN** `WorkflowContractError` names the task and `os` and no file is written

#### Scenario: Allowed import saved
- **WHEN** the same task contains `import json`
- **THEN** the workflow is saved

#### Scenario: Generated code deferred
- **WHEN** the task's `code` is `"{{code}}"`
- **THEN** save does not reject it

### Requirement: Runtime failures quote the contract
When `python_exec` code fails on a disallowed import or blocked builtin, the task failure message
SHALL include the contract text.

#### Scenario: Repair loop sees the rules
- **WHEN** code runs `import os`
- **THEN** the failure message contains `Module 'os' is not allowed` and the list of allowed modules

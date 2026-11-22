## 1. Contract module
- [x] 1.1 `zebra_tasks/compute/sandbox.py`: constants, `describe_contract()`, `check_code()`
- [x] 1.2 `PythonExecAction` uses it (aliases kept); failure message appends the contract
- [x] 1.3 Tests: allowed/blocked behaviour, `check_code` findings, runtime message

## 2. Prompt exposure
- [x] 2.1 `{{python_sandbox}}` root in `resolve_template` via `extras["__python_sandbox__"]`; add to `_RUNTIME_ROOTS`
- [x] 2.2 Set the extra wherever engines are built (AgentLoop, container, web, CLI)
- [x] 2.3 `compute.yaml` prompt uses it (bump `version`); test text matches `ALLOWED_MODULES`

## 3. Save-time enforcement
- [x] 3.1 `_check_contracts` runs `check_code` on literal `python_exec` code
- [x] 3.2 Tests: `import os` refused, `import json` saved, templated code not rejected
- [x] 3.3 Test: every shipped workflow and template is clean

## 4. Docs and delivery
- [x] 4.1 Update `specs/zebra-as-is.md`, `zebra-tasks/README.md`, `zebra-agent/AGENTS.md`
- [x] 4.2 ruff, full tests, `openspec validate python-exec-sandbox-contract --strict`

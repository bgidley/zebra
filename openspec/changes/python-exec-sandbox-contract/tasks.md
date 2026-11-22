## 1. Contract module
- [ ] 1.1 `zebra_tasks/compute/sandbox.py`: constants, `describe_contract()`, `check_code()`
- [ ] 1.2 `PythonExecAction` uses it (aliases kept); failure message appends the contract
- [ ] 1.3 Tests: allowed/blocked behaviour, `check_code` findings, runtime message

## 2. Prompt exposure
- [ ] 2.1 `{{python_sandbox}}` root in `resolve_template` via `extras["__python_sandbox__"]`; add to `_RUNTIME_ROOTS`
- [ ] 2.2 Set the extra wherever engines are built (AgentLoop, container, web, CLI)
- [ ] 2.3 `compute.yaml` prompt uses it (bump `version`); test text matches `ALLOWED_MODULES`

## 3. Save-time enforcement
- [ ] 3.1 `_check_contracts` runs `check_code` on literal `python_exec` code
- [ ] 3.2 Tests: `import os` refused, `import json` saved, templated code not rejected
- [ ] 3.3 Test: every shipped workflow and template is clean

## 4. Docs and delivery
- [ ] 4.1 Update `specs/zebra-as-is.md`, `zebra-tasks/README.md`, `zebra-agent/AGENTS.md`
- [ ] 4.2 ruff, full tests, `openspec validate python-exec-sandbox-contract --strict`

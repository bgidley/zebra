# Tasks

Branch: `f158/quarantine-unparseable-workflows`. Commits reference #158.

## 1. Library

- [x] 1.1 `parse_workflow_yaml()`; `add_workflow` rejects unparseable / non-mapping YAML
- [x] 1.2 `quarantine_unparseable()` called before library scans; `restore()` refuses stubs
- [x] 1.3 Tests in `zebra-agent/tests/test_library.py`

## 2. Investigation

- [x] 2.1 Identify the writer of `fire_retirement_calculator_1.yaml` (optimizer, pre-`744453e`)

## 3. Docs

- [x] 3.1 `specs/zebra-as-is.md`, `zebra-agent/AGENTS.md`

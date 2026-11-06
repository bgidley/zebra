## 1. Static validation
- [x] 1.1 Add `zebra/definitions/contracts.py` with reference extraction and `validate_contracts`
- [x] 1.2 Path-availability dataflow (must/may sets, cycles, synchronized joins)
- [x] 1.3 Unit tests for O1 and O2

## 2. Run time
- [x] 2.1 `resolve_template` records/logs unresolved refs in `__contract_violations__`
- [x] 2.2 `strict_templates` fails the task; engine tests (O3)

## 3. Structured outputs and subworkflows
- [x] 3.1 `llm_call` `output_schema` validation
- [x] 3.2 `subworkflow` `expects` check
- [x] 3.3 Tests for O4

## 4. Library and built-ins
- [x] 4.1 Call `validate_contracts` from `WorkflowLibrary.save`
- [x] 4.2 Fix built-in workflows; test that all pass (O5)

## 5. Docs
- [x] 5.1 Update `specs/zebra-as-is.md`, add `specs/workflow-contracts-design.md` and index it in `specs/AGENTS.md`

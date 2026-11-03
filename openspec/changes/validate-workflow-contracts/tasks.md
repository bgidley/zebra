## 1. Static validation
- [ ] 1.1 Add `zebra/definitions/contracts.py` with reference extraction and `validate_contracts`
- [ ] 1.2 Path-availability dataflow (must/may sets, cycles, synchronized joins)
- [ ] 1.3 Unit tests for O1 and O2

## 2. Run time
- [ ] 2.1 `resolve_template` records/logs unresolved refs in `__contract_violations__`
- [ ] 2.2 `strict_templates` fails the task; engine tests (O3)

## 3. Structured outputs and subworkflows
- [ ] 3.1 `llm_call` `output_schema` validation
- [ ] 3.2 `subworkflow` `expects` check
- [ ] 3.3 Tests for O4

## 4. Library and built-ins
- [ ] 4.1 Call `validate_contracts` from `WorkflowLibrary.save`
- [ ] 4.2 Fix built-in workflows; test that all pass (O5)
- [ ] 4.3 Terminal-route integration tests

## 5. Docs
- [ ] 5.1 Update `specs/zebra-as-is.md`, add `specs/workflow-contracts-design.md` and index it in `specs/AGENTS.md`

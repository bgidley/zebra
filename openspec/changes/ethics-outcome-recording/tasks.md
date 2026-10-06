## 1. Task actions

- [ ] 1.1 Add `record_ethics_review` action (normalise post-review, audit `post_review`) + entry point
- [ ] 1.2 Add `record_ethics_rejection` action (infer gate, set `ethics_rejection`) + entry point
- [ ] 1.3 Unit tests for both actions in `zebra-tasks/tests/`

## 2. Workflow

- [ ] 2.1 `agent_main_loop.yaml` v9: reorder tail, add `record_ethics_review`, give `ethics_rejection` its action
- [ ] 2.2 Extend `zebra-agent/tests/test_ethics_workflow.py` for rejection gates and post-review ordering

## 3. Surfacing

- [ ] 3.1 `AgentResult.ethics_rejection` + rejection error message in `loop.py`; tests in `test_loop.py`
- [ ] 3.2 `_extract_ethics_outcome` + `partials/ethics_outcome.html` on run detail/pending pages; unit test

## 4. Docs

- [ ] 4.1 Update `specs/zebra-as-is.md`

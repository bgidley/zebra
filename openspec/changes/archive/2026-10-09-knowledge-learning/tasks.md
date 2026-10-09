## 1. Actions

- [x] 1.1 Extract `store_knowledge_entry()` from `AddKnowledgeAction`; add optional `confidence`
- [x] 1.2 `extract_knowledge` action with key normalisation, existing-key reuse, privacy filters, cap
- [x] 1.3 `store_learned_knowledge` action: agent source, confidence cap, contradiction → resolve process (deduplicated)
- [x] 1.4 `execute_goal_workflow` result gains `user_inputs`
- [x] 1.5 `apply_resolution` `use_new` marks the entry human; register the two entry points

## 2. Agent main loop

- [x] 2.1 `agent_main_loop.yaml` v14: `record_ethics_review → extract_knowledge → store_learned_knowledge → report_outcome`

## 3. Web UI

- [x] 3.1 `/knowledge/`: source badge, confidence highlight, Confirm button, hide soft-deleted entries
- [x] 3.2 `POST /knowledge/<id>/confirm/`

## 4. Tests and docs

- [x] 4.1 Unit tests: extraction, storage, user inputs, main loop integration, web confirm
- [x] 4.2 Update `specs/zebra-as-is.md` and the package AGENTS.md files

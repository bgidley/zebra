## 1. Resolver

- [x] 1.1 `zebra.forms.resolve_task_schema()` + `SCHEMA_REF`
- [x] 1.2 Unit tests in `zebra-py/tests/test_forms.py`

## 2. Consumers

- [x] 2.1 `web_views._task_schema()` used by form, submit and both task lists; hide generated schemas from prior outputs
- [x] 2.2 `views.py`: complete-task validation and resolved `schema` in pending-tasks
- [x] 2.3 `execute_goal_workflow._extract_user_inputs`
- [x] 2.4 Web and `user_inputs` tests

## 3. Workflow creator

- [x] 3.1 Prompt section "Generated forms (follow-up questions)"
- [x] 3.2 `check_generated_workflow` rejects non-reference schema strings
- [x] 3.3 Creator tests

## 4. Docs

- [x] 4.1 `specs/zebra-as-is.md`, `zebra-py/AGENTS.md`, `zebra-agent-web/AGENTS.md`, root `AGENTS.md`

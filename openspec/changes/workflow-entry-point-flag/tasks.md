## 1. Library
- [ ] 1.1 Add `entry_point: bool = True` to `WorkflowInfo`; parse it in `_load_workflow_info` (warn on non-bool)
- [ ] 1.2 Add `is_entry_point()` and filter it in `list_goal_workflows`; update its docstring
- [ ] 1.3 Tests: hidden, default, malformed, save round-trip, sub-workflow still runs

## 2. Authoring guidance
- [ ] 2.1 Mention `entry_point` in the curator, optimizer and variant-creator prompts
- [ ] 2.2 Update `zebra-agent/AGENTS.md` and `specs/zebra-as-is.md`

## 3. Delivery
- [ ] 3.1 ruff check/format, full unit tests, pipeline green, archive change

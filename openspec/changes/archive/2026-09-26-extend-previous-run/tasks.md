> Branch: `f116/extend-goal`. Reference `#116` in commits.

## 1. Context propagation

- [x] 1.1 `zebra_tasks/agent/followup.py`: `build_previous_run_context`, `with_previous_run`, `previous_run_id`
- [x] 1.2 Apply `with_previous_run` in the selector, creator, variant creator, ethics gate (prompt only) and `execute_goal_workflow` (sub-workflow goal)
- [x] 1.3 `AgentLoop.process_goal` and `queue_goal` accept `previous_run_context`

## 2. Lineage & ownership

- [x] 2.1 `WorkflowRun.extends_run_id`, `WorkflowRunModel.extends_run_id` plus migration 0023, and both metrics stores
- [x] 2.2 `assess_and_record` / `record_metrics` record `extends_run_id`; run detail shows a "Follow-up to" link
- [x] 2.3 Scope `DjangoMetricsStore.get_run` to the current user

## 3. Web UI

- [x] 3.1 Goal form: dropdown of recent runs, HTMX preview (`/runs/<id>/context/`), and an `extend_from` lookup by ID
- [x] 3.2 Activity list "Extend" link
- [x] 3.3 One shared `_completed_run` / `_previous_run_context` helper for the execute, queue, form and preview views

## 4. Tests & docs

- [x] 4.1 Unit tests: helper, executor propagation, ethics gate prompt, `get_run` scoping, lineage persistence, cross-user and incomplete-run rejection, older-run preselect
- [x] 4.2 Update `specs/zebra-as-is.md`

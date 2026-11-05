> Branch: `f230/commons-import`. Reference `Refs #230` in commits (S3).

## 1. Export content

- [x] 1.1 Optional signed `display_name` and `golden_tasks` in the export content; `verify_export` returns them

## 2. Supervision state

- [x] 2.1 `WorkflowLibrary.record_supervised_run`, `clear_supervision`, `resupervise_adopted`, `is_supervised` (`.lineage/supervision.json`)
- [x] 2.2 Tests

## 3. Launch choke point

- [x] 3.1 `check_launch` → `SupervisedLaunch` / `LaunchRefused` (stopped); `create_library_process` creates the *Supervised run* wrapper
- [x] 3.2 `zebra_tasks/commons/supervised.py`: `supervised_run_definition`, `commons_supervised_run`
- [x] 3.3 `execute_goal_workflow` failover (`supervision_rejected`, `__excluded_workflows__`), selector exclusion, Agent Main Loop v19
- [x] 3.4 Tests per entry point; allowlist the wrapper's `create_process`

## 4. Gym import mode

- [x] 4.1 `run_golden_gym` `mode: import`: strict check, offer + local golden tasks, pass mark, escalate, never saves
- [x] 4.2 Tests

## 5. Import actions and workflow

- [x] 5.1 `commons_judge_import`, `commons_adopt`, `commons_import_review`, `commons_record_import`; entry points
- [x] 5.2 `zebra-agent/workflows/commons_import.yaml` (system)
- [x] 5.3 Tests

## 6. Web

- [x] 6.1 `__commons__` service (stop reason, held events) in engine extras
- [x] 6.2 Owner-only task completion (form + API)
- [x] 6.3 `/commons/` workflow upload → judged import; `commons_import --judge`
- [x] 6.4 Supervised badge + owner clear on the workflow library; emergency override re-supervises
- [x] 6.5 E2E: approve → supervised in library → goal and routine raise pre-run approval; PII rejected; `file_delete` escalates

## 7. Docs

- [x] 7.1 `specs/zebra-as-is.md`, `specs/zebra-commons-design.md` (as built), AGENTS.md files

## 8. Review fixes

- [x] 8.1 No name exempts a workflow from supervision (`supervision_for`); `Supervised run: ` reserved: judge and `save(writer="adopt")` refuse it; tests
- [x] 8.2 `definition_actions()`: task + process-level `construct_action` / `destruct_action` in `unsafe_reason` (strict and gate), the judge's registry check and `workflow_actions`; gym import-mode test with a `construct_action`

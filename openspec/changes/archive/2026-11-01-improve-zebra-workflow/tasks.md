> Branch: `f251/improve-zebra`. Reference `#251` in commits (`Part of #251`: slice C remains).

## 1. Workflow

- [x] 1.1 `zebra-agent/workflows/improve_zebra.yaml`: propose → outcome feedback → ship → recommend → review_pr (merge / changes / reject) → report; stage failures → propagate_failure
- [x] 1.2 Builder: `diff_excerpt` / `diff_truncated` on propose and ship results

## 2. Dream wiring

- [x] 2.1 `build` verdict (`ACCEPTED_VERDICTS`), `start_improvement_build` action + entry point, `issue_iid()`
- [x] 2.2 `zebra_improvement_request.yaml` v3 (`start_build`), `/dreams/` label

## 3. System-workflow protection

- [x] 3.1 `is_system_workflow()` shared by loader and curator; loader skips `system`-tagged workflows
- [x] 3.2 Optimizer rejects a generated workflow named after a system workflow

## 4. Tests

- [x] 4.1 Workflow test with a faked host builder: happy path, form fields, changes loop, reject, stage failures, internal-only
- [x] 4.2 `start_improvement_build`: build / linked issue / other verdicts / filing failure / rerun / `issue_iid`
- [x] 4.3 Loader and optimizer system-workflow tests; builder diff excerpt tests

## 5. Docs & delivery

- [x] 5.1 `specs/self-improvement-design.md`, `specs/AGENTS.md`, `specs/zebra-as-is.md`, `specs/claude-code-builder-design.md`, package AGENTS.md files
- [ ] 5.2 Zebra outcome feedback; push; green pipeline; merge; prod check; archive; outcome review

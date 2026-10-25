> Branch: `f237/leak-guard`. Reference `#237` in commits.

## 1. Implementation

- [x] 1.1 `zebra_tasks/agent/leak_guard.py`: `LeakHit`, `LeakGuard` (literals, detectors, allow text), `generalise_prompt()`, `describe_hits()`, `run_texts_from_metrics()`
- [x] 1.2 Creator: guard + one regeneration, keep and record remaining hits; prompt rule; `leak_guard` in output
- [x] 1.3 Variant creator: same, parent = source YAML
- [x] 1.4 Evaluator: `run_exposure` in the evaluation
- [x] 1.5 Optimizer: guard on create and modify (before gym staging), `failed_changes` with `leak_hits`, prompt rule
- [x] 1.6 Dream-cycle page shows leak hits on rejected changes

## 2. Tests

- [x] 2.1 Detector unit tests (each kind + negatives)
- [x] 2.2 Optimizer: Acme/Jane generalised; rejected after two copies; gym staging guarded
- [x] 2.3 Creator and variant: generalised, kept (never failed), topic words pass in one call
- [x] 2.4 Evaluator `run_exposure`
- [x] 2.5 Existing suites green; ruff check + format

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`, Commons design leak-guard section
- [x] 3.2 Outcomes on #237 + Zebra feedback
- [ ] 3.3 CI green, merge, deploy, outcome review, archive

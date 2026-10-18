## 1. Golden tasks & scores

- [x] 1.1 `zebra_agent/gym.py`: `GoldenTask`, `load_golden_tasks()`, `WorkflowLibrary.list_golden_tasks()`
- [x] 1.2 Golden task files for built-in workflows in `zebra-agent/golden/`
- [x] 1.3 `GymScore` dataclass; `MetricsStore.record_gym_scores` / `get_gym_scores`; in-memory backend
- [x] 1.4 `GymScoreModel` + migration, `DjangoMetricsStore`

## 2. Gym action & optimizer

- [x] 2.1 `run_golden_gym` action: select tasks, safety check, start children, suspend, judge, record
- [x] 2.2 Gate mode: compare candidate vs current, promote / reject, rewrite `optimization_results`
- [x] 2.3 `workflow_optimizer` `gym_gate` staging; shared `save_workflow_file`
- [x] 2.4 Entry point

## 3. Workflows

- [x] 3.1 `dream_cycle.yaml` v8: `golden_gym` step + summary section
- [x] 3.2 `golden_gym.yaml` system workflow (on demand)

## 4. UI

- [x] 4.1 `/gym/` page + nav item

## 5. Tests & docs

- [x] 5.1 Unit tests: loader, stores, action (degraded rejected, equal promoted, ungated, unsafe, no LLM, on-demand), optimizer staging, page
- [x] 5.2 `specs/golden-gym-design.md`, `specs/zebra-as-is.md`, AGENTS.md files

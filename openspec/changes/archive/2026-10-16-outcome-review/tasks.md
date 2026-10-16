Branch: `f190/outcome-review`

## 1. Actions

- [x] 1.1 `zebra_source` action (read / search, sandboxed root + allowlist)
- [x] 1.2 `compare_outcome_reviews` action (parse, compare, route, ruling mode)
- [x] 1.3 Entry points in `zebra-tasks/pyproject.toml`; `uv sync --all-packages`

## 2. Workflows

- [x] 2.1 `read_zebra_source.yaml`, `search_zebra_source.yaml` (tool-only)
- [x] 2.2 `outcome_review.yaml`

## 3. Running it

- [x] 3.1 `run_workflow` management command (+ `--status`)
- [x] 3.2 `scripts/zebra-outcome-review.sh`; `zebra-feedback.sh` reviews outcomes at start

## 4. Tests

- [x] 4.1 `zebra_source` tests, including sandbox escapes
- [x] 4.2 `compare_outcome_reviews` tests
- [x] 4.3 Workflow tests: agreed, agreed-after-reconsider, ruled
- [x] 4.4 `run_workflow` command tests

## 5. Process docs

- [x] 5.1 `openspec/config.yaml` outcomes rule; CLAUDE.md steps; `/cicd` + `cicd-manager`
- [x] 5.2 `specs/outcome-review-design.md`, `specs/AGENTS.md`, `specs/zebra-as-is.md`, package AGENTS.md

## 6. Deliver

- [x] 6.1 `uv run ruff check --fix . && uv run ruff format .`, unit tests
- [ ] 6.2 CI green → merge → deploy → run the outcome review on this feature itself

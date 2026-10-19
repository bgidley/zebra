Branch: `f211/zebra-source-list`

## 1. Action

- [x] 1.1 `zebra_source` `operation: list` (one level, or recursive by glob, capped)
- [x] 1.2 Read failures: nearest-path suggestions, list/search hint, undeployed top-level entry, directory listing
- [x] 1.3 Tests in `zebra-tasks/tests/test_zebra_source.py` (list, suggestions, hidden entries never named)

## 2. Workflows and deploy

- [x] 2.1 `list_zebra_source.yaml`; tool descriptions name deployed entries; *Outcome Review* offers the list tool
- [x] 2.2 `Dockerfile` runtime stage copies `specs/ docs/ openspec/ scripts/ deploy/` and root `*.md` (#212)
- [x] 2.3 Workflow tests updated (`test_outcome_review_workflow.py`)

## 3. Docs and checks

- [x] 3.1 `specs/outcome-review-design.md`, `specs/zebra-as-is.md`
- [x] 3.2 Run lint + format, full unit suite; `openspec validate zebra-source-list --strict`

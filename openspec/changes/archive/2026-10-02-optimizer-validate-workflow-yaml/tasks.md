> Branch: `f128/dream-optimizer-validate-yaml`. Reference `#128` in commits.

## 1. Implementation

- [x] 1.1 Optimizer: shared generate helper using `GENERATED_WORKFLOW_MAX_TOKENS`, with one retry on truncation
- [x] 1.2 Optimizer: validate (loader + `check_generated_workflow` + registered actions) before saving
- [x] 1.3 Optimizer: `failed_changes` output; rejected changes left out of `changes_made`
- [x] 1.4 Tolerate unterminated code fences in `_clean_yaml_response`
- [x] 1.5 `dream_cycle.yaml` v3: summary prompt includes `failed_changes`

## 2. Tests & docs

- [x] 2.1 Tests: truncated, truncated then retried, structurally invalid, unregistered action, valid and invalid mixed
- [x] 2.2 Update `specs/zebra-as-is.md`

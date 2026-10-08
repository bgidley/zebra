## 1. Library

- [x] 1.1 `retire` / `restore` / `list_retired_workflows` / `list_workflow_files` on `WorkflowLibrary`; retired files live in `retired/`
- [x] 1.2 `get_workflow` / `get_workflow_yaml` fall back to retired files; newest same-name copy wins
- [x] 1.3 `copy_builtin_workflows` skips retired built-ins
- [x] 1.4 `llm-defined` tag via `add_workflow(llm_defined=True)` / `tag_llm_defined`

## 2. Provenance

- [x] 2.1 Workflow creator and variant creator save with `llm_defined=True`
- [x] 2.2 Optimizer tags created workflows and keeps the original provenance on modify

## 3. Curator

- [x] 3.1 `workflow_curator` action: broken, superseded_copy, failing, unused, duplicate rules
- [x] 3.2 System protection, per-cycle cap, dry run, `ZEBRA_CURATOR_*` settings
- [x] 3.3 Register the entry point; add `curate_workflows` to `dream_cycle.yaml` (v5) before `load_workflows`; include it in the summary

## 4. Web UI

- [x] 4.1 Retired section with Restore on the library page
- [x] 4.2 Retire / Restore buttons and retired banner on the workflow detail page

## 5. Tests and docs

- [x] 5.1 Library, curator, optimizer/creator, dream-cycle and web view tests
- [x] 5.2 Update `specs/zebra-as-is.md` and the package AGENTS.md files

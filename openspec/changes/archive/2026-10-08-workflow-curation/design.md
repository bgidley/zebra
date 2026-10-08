## Context

The workflow library is a directory of YAML files (`ZEBRA_LIBRARY_PATH`, default `~/.zebra/workflows`). `list_workflows` globs `*.yaml` at the top level only. Workflow stats (`total_runs`, `success_rate`, `last_used`) come from `MetricsStore.get_all_stats()`. Nothing records whether a workflow was written by a person or by the LLM.

## Decisions

- **Retire = move to `retired/`.** The non-recursive glob already hides the subdirectory, so the selector, the LLM context and the dream cycle exclude retired workflows with no further changes. The retirement metadata (`reason`, `retired_at`, `superseded_by`) is appended after a marker comment. This keeps the original YAML intact and needs no sidecar file; `get_workflow_yaml` and `restore` strip it again. Retiring never deletes anything.
- **Lookup order:** active files first, newest mtime first, then retired files. This also makes same-name copies deterministic: before, the glob order was arbitrary.
- **Provenance by tag, not by location.** Workflows can be uploaded by hand through the web UI too, so "not built in" doesn't mean "LLM-written". `tag_llm_defined` re-dumps the YAML with multi-line strings as `|` blocks, so prompts stay readable. Workflows that existed before this change carry no tag and are treated as hand-written, which is the safe side.
- **Curator runs before `load_workflows`**, not after `evaluate_workflows` as the issue first sketched. That way the evaluator and optimizer never spend tokens on, or modify, workflows that are about to be retired.
- **The LLM only finds duplicate pairs; the code picks the loser** (lower `success_rate`, then fewer runs). This keeps the decision deterministic, and the LLM cannot retire a hand-written workflow.
- **Settings:** task property, then a `ZEBRA_CURATOR_*` env var, then a default. Task actions can't read Django settings; this follows the precedent of `kagi_search` and the notification actions, which read their configuration from env vars.

## Risks / Trade-offs

- A broken newest copy with a valid older copy: both are retired (broken, then superseded_copy), and either can be restored by hand. Rare.
- `unused` for a never-run workflow uses the file's mtime, which a manual edit resets. That's acceptable: a fresh edit is a sign the workflow is still wanted.
- Hard deletion of long-retired workflows is deferred (an open question on #148).

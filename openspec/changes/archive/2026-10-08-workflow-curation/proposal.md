## Why

Nothing ever removes a workflow from the library. LLM-created workflows (creator, variant creator, optimizer) pile up, the optimizer saves modified workflows as extra `foo_1.yaml` copies, and truncated or failing workflows stay selectable. #146 keeps every workflow the LLM defines, so curation belongs in the dream cycle. Issue #148.

## What Changes

- `WorkflowLibrary` gains **soft retirement**:
  - `retire(name, reason, superseded_by=None, path=None)` moves the YAML to `retired/` and appends the reason after a marker comment. The original text is kept byte-for-byte.
  - `restore(name)` moves it back.
  - `list_retired_workflows()` lists retired workflows.
  - `list_workflow_files()` lists every active file, including same-name copies.
  - Retired workflows are hidden from `list_workflows` (and so from the selector, `get_context_for_llm` and the dream cycle). `get_workflow` / `get_workflow_yaml` still resolve them, so history and continuations keep working.
  - `copy_builtin_workflows` does not bring back a retired built-in.
- **Provenance tag `llm-defined`**:
  - `add_workflow(..., llm_defined=True)` and the optimizer stamp it on workflows the LLM writes.
  - When the optimizer modifies a hand-written workflow, the result stays untagged.
- **New `workflow_curator` action** (dream cycle, before `load_workflows`). Rules, in priority order:
  - **broken:** fails to load or validate.
  - **superseded_copy:** an older same-name file.
  - **failing:** `total_runs >= min_runs` and `success_rate < min_success_rate`.
  - **unused:** `llm-defined` only; no run, or if never run no file change, within `unused_days`.
  - **duplicate:** an LLM judges two workflows to do the same job; the weaker one is retired, but only if it is `llm-defined`.
- **Curator safeguards:**
  - Workflows tagged `system`, and the core system workflows, are never touched.
  - A per-cycle cap; decisions beyond it are deferred.
  - Dry-run mode.
  - The report is stored as process property `curation` and summarised by the dream cycle.
- **Web UI:**
  - The library page lists retired workflows with their reason and a Restore button.
  - The workflow detail page has Retire / Restore buttons and a "Retired" banner.

## Capabilities

### New Capabilities
- `workflow-curation`: soft retirement of library workflows and the dream-cycle curator that decides what to retire.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-agent/zebra_agent/library.py`, `zebra-agent/workflows/dream_cycle.yaml` (v5)
- `zebra-tasks/zebra_tasks/agent/curator.py` (new; `workflow_curator` entry point), `creator.py`, `variant_creator.py`, `optimizer.py`
- `zebra-agent-web/zebra_agent_web/api/web_views.py`, `urls.py`; templates `pages/workflow_library.html`, `pages/workflow_detail.html`
- Additive: new `add_workflow` keyword with default `False`; new `WorkflowInfo.retired` field with default `None`. No migration (the library is file-based).

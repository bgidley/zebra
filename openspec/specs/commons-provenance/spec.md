# commons-provenance Specification

## Purpose
TBD - created by archiving change commons-provenance. Update Purpose after archive.

## Requirements

### Requirement: One save path
Every write of a workflow file into the library SHALL go through `WorkflowLibrary.save()`.
`add_workflow` and `save_workflow_file` SHALL delegate to it, and the optimizer and golden gym
SHALL save through it. `save()` SHALL never overwrite an existing file.

#### Scenario: Optimizer save goes through the library
- **WHEN** the dream-cycle optimizer saves a modified workflow
- **THEN** the new file holds a `commons` block written by the library

### Requirement: Canonical content hash
The library SHALL hash a workflow's canonical content: parsed with a `SafeLoader` without the
timestamp resolver, without the `commons` block, the top-level `name` and the tags
`llm-defined` and `system`, serialised as sorted compact JSON (`ensure_ascii=False`), UTF-8,
sha256. A workflow with no JSON form SHALL have no hash, with a reason.

#### Scenario: Rename keeps the hash
- **WHEN** a workflow is renamed or tagged `llm-defined`
- **THEN** its `content_sha256` is unchanged

#### Scenario: Unhashable YAML
- **WHEN** a workflow holds a non-string key or a `!!binary` value
- **THEN** hashing fails with a reason and the block's `content_sha256` is null

### Requirement: The commons block is library-owned
`save()` SHALL strip any `commons` block from the YAML it is given and write its own, and
`get_workflow_yaml()` SHALL return YAML without it, so no LLM writer sees or sets it.

#### Scenario: An LLM-supplied block is ignored
- **WHEN** a writer passes YAML with `commons: {foreign_users: false, share_with: [public]}`
- **THEN** the saved block is computed by the library and `share_with` is `[]`

### Requirement: Local-change rules
On a content change `save()` SHALL set `parent_sha256` to the previous hash, push it onto
`ancestors` (newest first, at most 32), clear `origin_pubkey`, add the library's sphere to
`tainted_by`, reset `share_with` to `[]` and keep `supervised`. A save with unchanged content
SHALL keep the previous block.

#### Scenario: Optimizer rewrite
- **WHEN** the optimizer rewrites a workflow whose hash is H
- **THEN** the new version has `parent_sha256: H`, `ancestors[0] == H` and `share_with: []`

### Requirement: Owner-only taint
`save()` SHALL set `foreign_users: true` when the writer's exposure holds runs of any user other
than the Commons owner, or any user while the owner is unknown. `foreign_users` SHALL be
inherited by every later version. `commons_exportable()` SHALL return false for such a workflow.

#### Scenario: Learnt from a second user's runs
- **WHEN** the optimizer rewrites a workflow after seeing runs of a user who is not the owner
- **THEN** the new version has `foreign_users: true` and `commons_exportable` is false

#### Scenario: Taint survives a clean rewrite
- **WHEN** a workflow with `foreign_users: true` is rewritten from owner-only runs
- **THEN** the new version still has `foreign_users: true`

### Requirement: Unknown provenance is foreign
A workflow file without a `commons` block (written before this change) SHALL be treated as
`foreign_users` unless its content hash matches a shipped built-in workflow. `commons_exportable()`
SHALL return false for any workflow without a block. A save whose parent has no block and is not
an unmodified built-in SHALL set `foreign_users: true`. A shown workflow without a block SHALL
taint the writer's exposure the same way.

#### Scenario: Legacy LLM-defined workflow rewritten from owner-only runs
- **WHEN** a blockless `llm-defined` workflow is rewritten by the optimizer from owner-only runs
- **THEN** the new version has `foreign_users: true` and `commons_exportable` is false

#### Scenario: Unmodified built-in stays clean
- **WHEN** a blockless file identical to a shipped built-in is edited from owner-only runs
- **THEN** the new version has `foreign_users: false`

#### Scenario: Legacy workflow shown to the optimizer
- **WHEN** the optimizer creates a workflow from owner-only runs while its prompt shows a blockless
  non-built-in workflow
- **THEN** the new workflow has `foreign_users: true`

### Requirement: Shown workflows carry their taint
When an LLM writer is shown other library workflows (the optimizer's `existing_workflows` and the
evaluator's `definitions_shown`), its exposure SHALL fold in their taint: `foreign_users` is set if
any of them has it, and their `tainted_by` spheres join the saved block's `tainted_by`. A shown
workflow whose block cannot be read SHALL count as foreign.

#### Scenario: New lineage from a foreign-tainted example
- **WHEN** the optimizer creates a new workflow from owner-only runs while its prompt shows a
  workflow with `foreign_users: true`
- **THEN** the new workflow has `foreign_users: true` and `commons_exportable` is false

#### Scenario: Evaluated definitions taint too
- **WHEN** the evaluator judged a workflow with `foreign_users: true` (`definitions_shown`) and
  the optimizer then creates a workflow
- **THEN** the new workflow has `foreign_users: true`

### Requirement: Leak guard at save
When the exposure holds texts, `save()` SHALL run the leak guard (#237) on the text added versus
the parent. With hits and a rejecting writer (the dream cycle), nothing SHALL be saved.

#### Scenario: Dream-cycle leak rejected at save
- **WHEN** the optimizer's YAML copies a name from its run exposure and reaches `save()`
- **THEN** `save()` raises and no file is written

### Requirement: Stamped and legacy workflows run
A workflow saved through the library (with a `commons` block) and a workflow file without a block
SHALL both be offered to the workflow selector and run to completion when selected.

#### Scenario: Stamped workflow runs
- **WHEN** a workflow saved with `add_workflow` is picked by `workflow_selector`
- **THEN** `execute_goal_workflow` runs it to completion and the goal process completes

#### Scenario: Legacy workflow runs
- **WHEN** a blockless workflow file is picked by `workflow_selector`
- **THEN** `execute_goal_workflow` runs it to completion and the goal process completes

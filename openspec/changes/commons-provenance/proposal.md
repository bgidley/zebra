## Why

The Zebra Commons (#41) needs to know, for every workflow, exactly what its content is and where
it came from before anything can be offered, exported or synced. Today four writers put workflow
files in the library by different routes (`add_workflow` for the creator and variant creator,
`save_workflow_file` for the optimizer and the gym), so there is no single place to stamp
provenance, and a workflow learnt from another user's runs could later leave the deployment.
This is S2a of #229 (S2b, signed export/import, follows separately). Refs #229.

## What Changes

- **One save path:** `WorkflowLibrary.save(yaml, *, writer, parent, exposure)`. `add_workflow` and
  `save_workflow_file` delegate to it; the optimizer and the gym save through the library.
- **Canonical hash:** a `SafeLoader` without the timestamp resolver, strip the `commons` block,
  the top-level `name` and the local tags `llm-defined` / `system`, then sorted compact JSON →
  UTF-8 → sha256. YAML with no JSON form (non-string keys, `!!binary`, sets, NaN) has no hash and
  a reason.
- **`commons:` block**, written only by the library: `content_sha256`, `parent_sha256`,
  `ancestors` (newest first, 32), `origin_pubkey`, `fork_of`, `adopted_at`, `supervised`,
  `sphere`, `tainted_by`, `share_with`, `foreign_users`. Readers (`get_workflow_yaml`, so every
  LLM writer's input) get the YAML without it.
- **Local-change rules:** new hash, previous hash as `parent_sha256` and pushed onto `ancestors`,
  `origin_pubkey` cleared, this sphere added to `tainted_by`, `share_with` reset to `[]`,
  `supervised` kept. Unchanged content keeps the block.
- **Owner-only taint:** an `Exposure` (run texts, goal texts, user ids of the runs the writer was
  shown) travels with every LLM write. Any user id other than the Commons owner (S1's
  `commons_owner_user_id`, else the first user) sets `foreign_users: true`, which only grows along
  a lineage. The analyzer and evaluator record the user ids behind `run_exposure`.
- **Leak guard inside save:** `save()` re-checks the exposure (#237); a dream-cycle writer
  (`reject`) gets nothing saved on a hit.
- `commons_exportable()` (S0, #245) also refuses `foreign_users`.

## Capabilities

### New Capabilities
- `commons-provenance`: the library's single save path, the canonical content hash and the
  `commons` provenance block.

### Modified Capabilities
<!-- None -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every workflow write goes through `WorkflowLibrary.save()`, which stamps a `commons` block | Unit tests: `add_workflow`, `save_workflow_file`, the optimizer and the gym promotion each produce a file with a `commons` block; no other code in `zebra-tasks`/`zebra-agent` writes workflow files to the library (grep for `write_text`/`open(…, "w")` in the save paths) |
| O2 | The content hash is canonical: renaming, retagging `llm-defined`/`system`, re-dumping the YAML or a date-like string do not change it; any real content change does; unhashable YAML is refused with a reason | Unit tests in `test_provenance.py` |
| O3 | An optimizer rewrite records lineage: `parent_sha256` = the old hash, the old hash first in `ancestors` (capped at 32), `share_with: []`, `origin_pubkey` cleared, this sphere in `tainted_by` | Unit test of the optimizer saving a modification; E2E-style test from the issue |
| O4 | A workflow learnt from another user's runs has `foreign_users: true`, it is inherited by later versions, and `commons_exportable` is false | Unit tests: creator with a non-owner `__user_id__`, optimizer with a non-owner in `run_exposure_users`, then a clean rewrite keeps the flag |
| O5 | In prod, workflows saved after deploy carry the block and nothing else changes for users | After the first prod dream cycle or new workflow: the saved file has a `commons` block with a hash; goals still select and run it (rollout check, not a gate) |

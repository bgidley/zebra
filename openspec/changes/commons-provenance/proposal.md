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
| O1 | Every workflow write goes through `WorkflowLibrary.save()`, which stamps a `commons` block; a rejected save writes nothing | Unit tests: `add_workflow`, `save_workflow_file`, the optimizer, the gym promotion, the creator and the variant creator each produce a file with a `commons` block; a save-time leak-guard rejection leaves the library unchanged; no other library write path remains (`save` is the only `write_text` of a new workflow) |
| O2 | The content hash is canonical: renaming, retagging `llm-defined`/`system`, re-dumping the YAML or a date-like string do not change it; any real content change does; unhashable YAML (non-string key, `!!binary`, NaN) has no hash and a reason | Fixture pairs in `test_provenance.py` |
| O3 | A rewrite records lineage: `parent_sha256` = the old hash (computed from the old content when it has no block yet), the old hash first in `ancestors` (capped at 32), `share_with: []`, `origin_pubkey` cleared, this sphere in `tainted_by`, `supervised` kept | Unit tests of `next_block` and of the optimizer saving a modification |
| O4 | A workflow learnt from another user's runs has `foreign_users: true`, inherited by later versions, and `commons_exportable` is false; with no owner known any user's runs count (fail closed) | Unit tests: creator with a non-owner `__user_id__`, optimizer with a non-owner in `run_exposure_users`, a clean rewrite keeps the flag, unknown owner taints |
| O5 | Nothing else changes for users: files without a block still load, list and get selected; stamped workflows load and run; readers (`get_workflow_yaml`) never return the block | Unit tests (legacy file, stamped file through `get_workflow` / `list_workflows`); in prod, the first workflow saved after deploy has a block with a hash and still runs |

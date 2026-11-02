## Why

#229 made `WorkflowLibrary.save()` the one path that writes a workflow's `commons` provenance
block, but two writers still bypass it: `copy_builtin_workflows` installs shipped workflows with
`shutil.copy`, and `restore()` writes the retired text straight back. So built-ins land without a
block (only recognised later by a hash match), and a restored blockless workflow stays blockless.
Nothing may reach the Commons (#236, #231) without provenance. Follow-up of #229 O1; Refs #269.

## What Changes

- `copy_builtin_workflows` writes each installed built-in with a **built-in block**: its content
  hash, no parent or ancestors, this deployment's `sphere`, `tainted_by: []` (no run data shaped
  it), `foreign_users: false`. Which files are installed, upgraded, kept retired or retired as
  stale copies is unchanged (#148, #224).
- An installed built-in **without a block whose content is the shipped content** (prod today) is
  stamped in place on the next start, keeping its mtime so "newest file wins" is unchanged.
- `restore()` keeps the block the retired file had; a blockless one gets a re-derived block: the
  built-in block if its hash is a shipped built-in's, else a root block with
  `foreign_users: true` (unknown lineage fails closed, as `legacy_block`).
- New pure helper `provenance.builtin_block(content_hash, sphere)`.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every built-in installed or upgraded by `copy_builtin_workflows` carries a `commons` block with its content hash, `foreign_users: false`, this deployment's sphere | Unit tests in `test_provenance.py`; after deploy, a read-only check in the `zebra-web` container finds on every non-system built-in a block whose hash equals the recomputed content hash, `foreign_users: false`, the deployment's sphere |
| O2 | Built-ins already installed without a block (prod) are stamped on the next start without changing which file is current | Unit tests: blockless unmodified copy gets stamped with mtime unchanged, a newer dream copy stays the current file, a modified blockless copy is left alone, a second start changes nothing; prod check as O1 |
| O3 | The install / upgrade / stays-retired / stale-copy rules (#148, #224) behave exactly as before | Existing `test_library.py` built-in tests pass unchanged |
| O4 | Restoring a retired workflow keeps its block; a blockless one gets a re-derived block (built-in clean, otherwise `foreign_users: true`) | Unit tests on `restore()`: block kept, blockless built-in clean, blockless custom workflow `foreign_users: true`, read back from disk |

## Capabilities

### Modified Capabilities
- `commons-provenance`: built-in installs and restores also carry the `commons` block.

## Impact

`zebra-agent/zebra_agent/library.py`, `zebra-agent/zebra_agent/provenance.py`, tests,
`specs/zebra-as-is.md`, `zebra-agent/AGENTS.md`. No data model or API change.

> Branch: `f269/stamp-builtins`. Reference `Refs #269` in commits.

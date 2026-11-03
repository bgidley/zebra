## Context

`save()` never overwrites (a taken name gets `_N`) and derives lineage from the newest active
file with the same name, which may be a dream copy. Built-in installs must overwrite the
installed copy in place and must not pick up a dream copy's lineage, so routing them through
`save()` would change the #224 rules. They are stamped instead.

## Decisions

- **Stamp, don't save.** `copy_builtin_workflows` writes `with_commons(shipped_text, block)` to
  the same `dest` it used to `shutil.copy` to. The decision logic (versions, retired, stale
  copies) is untouched.
- **Built-in block** (`provenance.builtin_block`): `content_sha256` = shipped hash,
  `parent_sha256` null, `ancestors []`, `sphere` = library sphere, `tainted_by []` (a built-in
  saw no run data), `share_with []`, `supervised false`, `foreign_users false`. The hash ignores
  the block, so `builtin_hashes()` still recognises a stamped copy, and `save()` of a change to
  it inherits `foreign_users: false` via the existing rules.
- **Backfill.** When the installed copy is current (not upgraded), has no block, and its hash
  equals the shipped hash, it is stamped in place and its `atime`/`mtime` restored, so the
  newest-file ordering (`_read_named`) and so which copy is current is unchanged. A modified
  blockless copy is not touched (it stays legacy → `foreign_users`).
- **Restore.** The text before the retired marker already holds the block if the file had one.
  If not: hash in `builtin_hashes()` → `builtin_block`; otherwise a root `next_block` with
  `foreign=True` (unknown lineage fails closed, same as `legacy_block`).
- The sphere is the library's at install time; the web app resolves it (`refresh_owner()`)
  before `install_builtin_workflows`.

## Risks

- A built-in already installed at an older version without a block, whose shipped version did
  not move, cannot be matched (its hash is not a shipped one) and stays legacy. Prod upgrades
  built-ins on start, so none are expected; the post-deploy check will show it.

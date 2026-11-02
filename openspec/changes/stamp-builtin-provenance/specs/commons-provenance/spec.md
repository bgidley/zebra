## ADDED Requirements

### Requirement: Built-ins are installed with provenance
`copy_builtin_workflows` SHALL write every built-in it installs or upgrades with a `commons`
block holding its content hash, no parent or ancestors, the library's sphere, an empty
`tainted_by` and `foreign_users: false`. Which built-ins it installs, upgrades, keeps retired or
retires as stale copies SHALL be unchanged.

#### Scenario: New built-in is stamped
- **WHEN** a built-in is copied into an empty library
- **THEN** the installed file has a `commons` block whose `content_sha256` is the shipped content's hash and `foreign_users` is false

#### Scenario: Upgraded built-in is stamped
- **WHEN** a built-in ships at a higher version than the installed copy
- **THEN** the replacement file has a `commons` block with the new content's hash

### Requirement: Blockless installed built-ins are backfilled
On install, an active built-in copy with no `commons` block whose content hash equals the
shipped built-in's SHALL be stamped in place, keeping its modification time. A blockless copy
with different content SHALL be left unchanged.

#### Scenario: Unmodified blockless copy
- **WHEN** the library holds the shipped built-in without a block and the version has not moved
- **THEN** the file gets the built-in block and its mtime is unchanged

#### Scenario: Modified blockless copy
- **WHEN** the installed copy's content differs from the shipped built-in and the version has not moved
- **THEN** the file is not modified

### Requirement: Restore keeps or re-derives provenance
`restore()` SHALL keep the `commons` block the retired file had. A retired file without one SHALL
be restored with a re-derived block: the built-in block when its hash is a shipped built-in's,
otherwise a block with its hash and `foreign_users: true`.

#### Scenario: Restore keeps lineage
- **WHEN** a workflow saved with a parent is retired and restored
- **THEN** the restored file has the same `commons` block

#### Scenario: Restore of a blockless workflow
- **WHEN** a retired workflow without a block, not a built-in, is restored
- **THEN** the restored file has a block with its content hash and `foreign_users: true`

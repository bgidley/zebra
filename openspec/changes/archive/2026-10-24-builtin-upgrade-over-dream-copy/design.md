## Context

`copy_builtin_workflows(builtin_path)` runs at web/daemon startup (`install_builtin_workflows`).
Per built-in file it copies it if missing, or overwrites it if the shipped `version` is higher,
and skips it if `retired/<same filename>` exists (#148). The library resolves a name to the newest
active file by mtime, so a dream copy `<name>_1.yaml` wins over an older built-in. The curator
then retires the older built-in as a `superseded_copy`.

## Decision

Make the retired check version-aware, and treat installing a newer built-in as the moment its
dream copies go stale.

1. If `retired/<file>` exists and the shipped version is not higher than its version, skip, as
   before. If one of the active same-name files is not the built-in, log a warning that the
   built-in is shadowed.
2. If the shipped version is higher, rename `retired/<file>` to `<stem>.builtin-v<N>.yaml`
   (`_free_path` if taken) and install the built-in.
3. After any install of a newer version (cases 2 and "dest exists with a lower version"),
   `retire()` every other active file with that workflow name, with `superseded_by=<name>`.
   A fresh install where `dest` was missing and nothing was retired retires nothing extra:
   any same-name copy there was not based on an older built-in we know about.

The rename keeps the old version visible in the retired list (`list_retired_workflows` reads all
`*.yaml`) and in name lookups for history, and it makes step 2 idempotent: the next startup
finds no `retired/<file>` and an up-to-date `dest`.

## Risks

- A user who deliberately retired a built-in gets it back when a newer version ships. That's
  acceptable, because a version bump is a deliberate change. They can retire it again.
- Dream copies reuse version numbers that later built-ins will need. Definition ids are
  `sha256(name:version)` and saved with `update_or_create`, so a built-in shipped at a dream
  copy's version shares its stored row. That is harmless for new runs, which load the library
  YAML, but a process parked on the other variant would load the wrong steps. Bump past any
  live dream copy's version, as *Read Zebra Source* v5 does here.
- Rename/copy/retire are separate file operations. If startup dies between the rename and the
  copy, the next startup does a fresh install and leaves the dream copies alone. The curator
  then retires the older of the same-name files.
- A dream copy that improved on the old built-in is retired. It stays restorable, and the next
  dream cycle can re-derive an improvement from the new built-in, which goes through the gym.

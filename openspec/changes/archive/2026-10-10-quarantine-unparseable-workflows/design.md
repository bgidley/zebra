# Design

## Decisions

1. **Reuse retirement, not a new quarantine folder.** `retired/` already has UI listing, metadata and
   "don't bring it back" handling in `copy_builtin_workflows`. An unparseable file can't carry the
   appended retirement block (the file would still not parse), so the stub wraps the raw text in a
   parseable mapping instead. The `.unparseable.yaml` filename means a corrupt user copy of a built-in
   does not block the built-in from being copied again.
2. **Scan where the library is read.** `list_workflows`, `_files_named` (`get_workflow`,
   `get_workflow_yaml`, `retire`, `restore`) and `list_workflow_files` call
   `quarantine_unparseable()` first. Moved files never reach a later scan, so the "re-parsed and
   logged on every load" behaviour stops after the first load.
3. **Distinct stub name.** `<name> [unparseable]` never shadows or resolves to a real workflow.
   `get_workflow` cannot load the stub (no tasks), so selection never picks it.
4. **Write-side guard.** `add_workflow` validates with `parse_workflow_yaml`. The creator and variant
   creator already parse with `load_definition_from_yaml` before saving. The optimizer validates with
   `_validate_workflow_yaml` (since `744453e`) before `_save_workflow`.

5. **Concurrent scans.** The web and daemon containers share the library. The file is claimed with an
   atomic `rename` into `retired/` before the stub is written. A scan that loses the race gets
   `FileNotFoundError` and skips, so there is never a duplicate stub or a crash (from Zebra's review).

## Risks

- A file being written at the moment of a scan could look truncated. Workflow writes are a single
  `write_text` of a small file, so the window is tiny, and the raw text is kept in the stub.

# Proposal

Closes #158

## Why

Prod's workflow library holds `fire_retirement_calculator_1.yaml`, a workflow cut off mid-string. Every
library load re-parses it and logs `found unexpected end of stream`. The Dream Cycle curator (#148)
retires broken workflows, but it only sees files that parse, so this file was never cleaned up.

It was written at 2026-10-02 19:57 UTC by `workflow_optimizer._save_workflow`, during a Dream Cycle
started at 19:55:48. The optimizer's YAML validation (`744453e`, 20:06) was not deployed yet. So this
is a leftover, but nothing stops the next bad file from staying forever either.

## What Changes

- `WorkflowLibrary.quarantine_unparseable()` runs before every scan of the active library (listing,
  name lookup, curator file list). A `*.yaml` that does not parse, or is not a mapping, moves to
  `retired/<stem>.unparseable.yaml`. The file becomes a parseable stub with:
  - name `<recovered name> [unparseable]`
  - tag `unparseable`
  - the raw text in `unparseable_content`
  - retirement metadata with reason `unparseable: <error>`
  It is logged once at WARNING and never re-parsed. Only the library directory is scanned, not the
  built-in workflows shipped in the repo.
- The stub shows in the retired list on `/workflows/` (and its raw text on the detail page). It is
  never selected or loaded, and `restore()` refuses it (409 in the UI): the YAML must be fixed and
  added again.
- `add_workflow` refuses YAML that does not parse or is not a mapping (`ValueError`), via the new
  `parse_workflow_yaml()`.

## Capabilities

### Modified Capabilities
- `workflow-curation`: unparseable library files are retired automatically.

## Impact

- `zebra-agent/zebra_agent/library.py`, `zebra-agent/tests/test_library.py`

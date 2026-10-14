See [specs/run-trace-design.md](../../../../specs/run-trace-design.md) for the narrative design.

## Decisions

- **Diff against the last journalled state, not just around the action.** The engine keeps the
  last journalled properties per process in memory and diffs each event against it, so changes
  made between steps (a parent writing into a child, a human task output) are still recorded
  and replay stays exact. After a restart the baseline is rebuilt by replaying stored events.
- **Strictly increasing timestamps per engine** so events order deterministically without a
  sequence column.
- **Journal is best effort.** A failure to write it logs a warning; execution never depends on
  it.
- **Cap values at 16k chars of JSON** (2k preview kept) so a large blob is not copied into
  every step.
- **Trace builder uses only `StateStore`**, so it works on every backend and is unit-tested on
  the in-memory store.

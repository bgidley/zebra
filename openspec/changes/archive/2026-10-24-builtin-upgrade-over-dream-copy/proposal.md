## Why

A dream-cycle copy of a built-in workflow can shadow the built-in on prod for good, so shipped
changes to that built-in never deploy. The optimizer saves a modified built-in as
`<name>_1.yaml`; the curator then retires the older built-in to `retired/<name>.yaml`
(`superseded_copy`); and `WorkflowLibrary.copy_builtin_workflows` skips every built-in that has a
file in `retired/` (#148), even when the shipped version is higher. On 2026-10-20 this left a
broken dream copy of *Read Zebra Source* running after #221 shipped v3. Every outcome-review
source read until the hand repair on 2026-10-23 returned junk. Closes #224.

## What Changes

- **A newer shipped built-in beats an old retirement**: when the shipped version is higher than
  the version of `retired/<file>`, startup installs the built-in and renames the retired file
  `<stem>.builtin-v<N>.yaml`, so it stays in the retired list but no longer blocks. A retired
  built-in whose shipped version is not higher stays retired (#148 unchanged).
- **Dream copies of an upgraded built-in are retired**: whenever startup installs a newer
  built-in version (over a retired copy or an older active one), every other active file with
  the same workflow name is retired with reason `built-in v<N> shipped (#224)` and
  `superseded_by` the built-in. They were based on the older built-in.
- **Shadowing is logged**: startup logs a warning for each built-in that stays retired while an
  active same-name copy runs in its place, naming the copy and both versions.

- *Read Zebra Source* goes to v5 with no change to its steps. On prod, the dream cycle wrote a new
  copy (v4) on 2026-10-24 that fails on every call. The bump replaces it on deploy. v4 is skipped
  because the dream copy's definition id (`sha256(name:version)`) already uses it.

## Non-goals

- Changing the curator or optimizer. Dream improvements to a built-in still win until the next
  built-in version ships.
- Surfacing shadowed built-ins on `/dreams/`. The log line is enough for now.
- Repairing prod by hand. The 2026-10-23 repair already matches the new layout.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A shipped built-in with a higher version replaces a retired older built-in and its dream copy | Test: built-in v2 retired in favour of dream copy `flow_1.yaml` v3; shipping built-in v3 makes `get_workflow` load the built-in, moves `flow_1.yaml` to `retired/` (reason names #224), and keeps the old v2 file as `retired/flow.builtin-v2.yaml` |
| O2 | Retirements of the same or an older version are still respected, and reinstalling is idempotent | Tests: `test_copy_builtin_skips_retired` still passes; a retired v3 with shipped v3 stays retired; running the copy twice after an upgrade copies nothing the second time and retires nothing more |
| O3 | Upgrading an active built-in also retires its dream copies, however many there are | Test: active `flow.yaml` v2 plus newer dream copies `flow_1.yaml` v3 and `flow_2.yaml` v4; shipping v3 overwrites `flow.yaml` and retires both copies, whatever their version |
| O4 | A built-in still shadowed at startup is logged | Test: built-in v2 retired, shipped v2, active dream copy → one warning naming the built-in, the copy and both versions; no warning when no copy runs in its place |
| O5 | It fixes prod | After deploy: prod's dream copy `read_zebra_source_1.yaml` v4 (broken since 2026-10-24 03:04: `SyntaxError` on every call) is in `retired/` with a #224 reason; `manage.py run_workflow "Read Zebra Source"` on `zebra-agent/zebra_agent/budget.py` succeeds on built-in v5; startup logs *Brainstorm Ideas* and *Web Research* as shadowed |

(Zebra outcome feedback received. Made O5 concrete and falsifiable, and added the many-copies case
to O3. Kept O4, because the issue asks for shadowing to be logged. Not adopted: keeping a dream
copy whose version is higher than a newly shipped built-in. Dream copies number their versions
from the older built-in, so the numbers can't be compared, and a shipped bump is the deliberate
signal.)

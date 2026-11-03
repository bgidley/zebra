## Why

The Wave 1 Commons outcome reviews (#245, #228, #229) left three gaps where a property was
assumed rather than proven:

- **#267** — `claude_code_build` is hinted `always_reversible`, but since #251 its `ship` and
  `merge` delivery stages ask the builder sandbox to push a branch and merge to master. Strict gym
  mode and trust gates trust that hint. The hint test also accepts a hint inherited from a
  non-`TaskAction` base (the git actions inherit `_GitAction`'s), which the spec says it should not.
- **#268** — "keys survive a restart" was tested with a second `FileCredentialStore` in the same
  process, and the Commons-off test does not cover the import and revoke actions.
- **#270** — no stamped workflow has been executed end to end, the selector was never shown
  picking a legacy (blockless) workflow, and prod had no post-deploy save to check.

Refs #267, #268, #270 (epic #41, design `specs/zebra-commons-design.md`).

## What Changes

- `claude_code_build` becomes `context_dependent` (its `patch` / `propose` / `review` stages stay
  inside the sandbox, `ship` / `merge` publish), joins `WRITERS`, and leaves `REVERSIBLE_WRITERS`.
  The hint test fails if any `always_reversible` action's module submits a builder job.
- Every registered action declares `reversibility_hint` on its own class: the git actions each
  state theirs, and `_GitAction` no longer carries one (a new git action without a hint falls back
  to `context_dependent` and fails the test).
- A subprocess test writes the Commons identity in one Python process and reads it back in a fresh
  one over the same key directory: same npub, and the device's cert chain verifies.
- The Commons-off web test also asserts 404 for the import and revoke POSTs (all six actions).
- Commons off over existing keys: all six actions 404, keys unchanged.
- A test runs a stamped (library-saved) workflow end to end through `workflow_selector` +
  `execute_goal_workflow`, and one where the selector picks a legacy blockless workflow.
- A read-only prod check for a workflow saved since 68516eb with a `commons` block, posted on #270.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `commons-safety`: honest builder hint; no inherited hints.
- `commons-identity`: keys proven across a process restart; all six actions off when disabled.
- `commons-provenance`: stamped and legacy workflows are selected and run.

## Outcomes

Tightened after Zebra's advisory feedback: O2 over the whole registry, O3 on the first process's
cert, O4 also over existing keys, O5 reports "pending" rather than passing when prod has no save.

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | No action that can push or merge code is hinted `always_reversible`: `claude_code_build` is `context_dependent`, so strict gym mode refuses a workflow using it | `test_launch.py`: `claude_code_build` in `WRITERS`, not in `REVERSIBLE_WRITERS`; `unsafe_reason(..., strict=True)` refuses it; a test fails if any `always_reversible` action's module calls `submit_build` |
| O2 | Every registered action states its own hint; none is inherited from a base class | `test_action_declares_its_own_hint`, parametrised over the whole registry (entry points + defaults), checks `vars(cls)` only; it passes, including the six git actions that used to inherit |
| O3 | Commons keys survive a real process restart | A test writes the identity in one subprocess and reads it in a fresh subprocess over the same key dir: both exit 0, same npub and device pubkey, and the `DEVICE_CERT` signed by the first process verifies in the second against the reloaded (not regenerated) keys |
| O4 | With `COMMONS_ENABLED` off every Commons action (start, pair, import, revoke, backup, restore) returns 404 and creates no key | `test_off_by_default_creates_nothing` posts all six and checks no key dir; a second test turns Commons off over existing keys and checks all six return 404 and the keys are unchanged |
| O5 | Stamped and legacy workflows are both selected and run; prod state is known | Tests: a library-saved (stamped) workflow and a blockless one each picked by `workflow_selector` and completed by `execute_goal_workflow`; a read-only prod check (deployed revision, newest workflow file and save time, its `content_sha256` recomputed, whether a goal ran it) posted on #270; if nothing has been saved yet it is reported as pending, not passed |

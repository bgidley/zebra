## Why

S2b (#229) can verify a signed workflow file and adopt it, but adoption is a single owner command
with no judging: nothing scans it for personal data, ethics-checks it, tests it on golden tasks or
asks the owner in the UI, and an adopted workflow's `supervised: true` flag is never enforced, so
an imported workflow runs like a local one the moment a goal selects it. S3 of the Zebra Commons
(#230, epic #41, `specs/zebra-commons-design.md` *Import* and *Supervised use*) adds the judged
import pipeline and enforces supervised use at the S0 launch choke point. Refs #230.

## What Changes

- **`Commons Import` workflow** (`zebra-agent/workflows/commons_import.yaml`, system, protected):
  `commons_judge_import` (verify the signed file, validate the YAML, every action registered, no
  name clash) → `commons_pii_scan` (fails closed) → `ethics_gate` (plan review) →
  `run_golden_gym` in **import mode** → `trust_gate` (domain `sharing`) → `commons_adopt` →
  `commons_record_import`. Each rejection is recorded with its stage and reason; nothing is saved.
- **Gym import mode** (`run_golden_gym` with `mode: import`): only the candidate runs, on the
  offer's `golden_tasks` plus local golden tasks for the same capability, scored against their
  criteria. Strict `unsafe_reason` (only `always_reversible` actions); anything else, no runnable
  golden tasks, no judge or an unscored run **escalates** to the owner without running; never
  "ungated" and never saves (`commons_adopt` is the only library writer). Routes `passed` /
  `rejected` / `escalate`.
- **`commons_adopt`**: `WorkflowLibrary.save(writer="adopt")` as `<name> (from <publisher display
  name>)`, `supervised: true`; re-verifies the file and refuses while the Commons is stopped.
- **Export file** gains optional signed `display_name` and `golden_tasks` (content keys).
- **Supervised use at the choke point**: `check_launch` returns a `SupervisedLaunch` for a library
  workflow whose `commons.supervised` is set; `create_library_process` then creates a generated
  *Supervised run* wrapper process instead: a human task "Run imported workflow X for this goal?"
  listing its actions with irreversible ones flagged (`reversibility_hint`), then
  `commons_supervised_run` starts the real workflow (or fails as rejected). Covers goals, direct
  runs, routines, `subworkflow`, `parallel_subworkflows` and `llm_agent` tools. A rejected goal run
  fails over to the selector's next choice (`supervision_rejected` route, excluded workflows).
  The flag clears after `SUPERVISED_RUNS` (3) approved successful runs or when the owner clears it.
- **Owner only**: tasks marked `owner_only` (import approval, supervised-run approval) can only be
  completed by the Commons owner (web form and API). The kill switch and Commons-off refuse
  imports, adoption and supervised launches; the emergency override re-supervises every adopted
  workflow.
- **Web**: owner uploads a file on `/commons/` to start a judged import; `manage.py commons_import
  F --judge` does the same; the workflow library shows "Supervised" with an owner "Clear" action.

## Capabilities

### New Capabilities
- `commons-import`: the judged import pipeline, gym import mode, adoption naming, supervised
  pre-run approval at the launch choke point, owner-only approvals and stop conditions.

### Modified Capabilities
<!-- None: commons-export gains optional signed content keys, its requirements are unchanged -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A signed workflow file uploaded by the owner runs through `Commons Import`; after the owner approves the trust-gate task the workflow is in the library as `<name> (from <publisher>)` with `supervised: true` and its hash kept | E2E test (web): upload → owner approval task → library file + block; unit tests of `commons_judge_import` / `commons_adopt` |
| O2 | Every rejection is recorded on the import run (`commons_import_result`: status, stage, reason; PII findings masked) and writes no library file: personal data in a prompt is rejected at stage `pii`; a tampered file, unregistered action, taken name or stopped Commons at `judge`; a low gym score at `gym`; the owner's refusal at `owner` | E2E test (PII file → `status: rejected`, stage `pii`, no adopted file); `zebra-agent/tests/test_commons_import.py` per stage |
| O3 | Gym import mode never runs a workflow that uses any non-`always_reversible` action (e.g. `file_delete`) and never treats "no golden tasks" as passing: both escalate to the owner with no gym child process; otherwise it scores the candidate on the offer's golden tasks plus local ones for the same capability against a pass mark (0.6), and it never writes the library | `zebra-tasks/tests/test_gym_import_mode.py`; E2E `file_delete` file escalates with no child process |
| O4 | Starting a supervised workflow from any entry point (goal, routine, direct run, subworkflow, parallel, llm_agent tool) raises exactly one owner-only "Run imported workflow X?" task listing its actions with irreversible ones flagged, and nothing of it runs (no process) before approval; a non-owner is refused (403); rejecting a goal's run fails over to the selector's next choice; ordinary workflows are unaffected | `zebra-agent/tests/test_supervised_launch.py` per entry; E2E goal + routine; web owner-only tests |
| O5 | The supervised flag clears after 3 approved successful runs (failed or refused runs never count; the count is local, keyed by content hash, and the hash and definition id do not change) or an owner clear; the kill switch / Commons-off refuse imports, adoption and supervised launches; the emergency override re-supervises adopted workflows | Library + launch unit tests; web stop-reason and pause-all tests |

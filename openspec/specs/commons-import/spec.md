# commons-import Specification

## Purpose
TBD - created by archiving change commons-import. Update Purpose after archive.

## Requirements

### Requirement: Judged import pipeline
The `Commons Import` system workflow SHALL take a signed export file and run, in order: the
judge (signature and chain verification, YAML validation, every action registered, no name
clash), `commons_pii_scan`, the ethics gate, the gym in import mode, the `sharing` trust gate and
`commons_adopt`. Any gate rejecting SHALL end the import with `commons_import_result` holding
`status: rejected`, the stage and the reason, and SHALL save nothing to the library.

#### Scenario: Owner approves an import
- **WHEN** a valid signed file passes every gate and the owner approves the trust-gate task
- **THEN** the workflow is in the library as `<name> (from <publisher display name>)` with
  `supervised: true` and the offered content hash, and `commons_import_result.status` is `adopted`

#### Scenario: Personal data in a prompt
- **WHEN** the imported workflow's prompt holds personal data
- **THEN** the import is rejected at stage `pii` with the scan's reason and no file is written

#### Scenario: Tampered file
- **WHEN** the file does not verify
- **THEN** the import is rejected at stage `judge` with the verification reason

#### Scenario: Unregistered action
- **WHEN** the workflow uses an action this deployment does not have, as a task action or as a
  task or process-level `construct_action` / `destruct_action`
- **THEN** the import is rejected at stage `judge`

#### Scenario: Reserved name
- **WHEN** the workflow is named like a *Supervised run* wrapper (`Supervised run: …`)
- **THEN** the import is rejected at stage `judge` and the library refuses to adopt that name

### Requirement: Gym import mode
In import mode the gym SHALL run only the candidate workflow, on the offer's golden tasks plus
local golden tasks for the same capability, scored against their criteria, and SHALL never save
to the library. It SHALL escalate to the owner, without running anything, when the workflow uses
any action that is not `always_reversible` (task actions and task or process-level
`construct_action` / `destruct_action`), when there are no runnable golden tasks, or when it
cannot judge; it SHALL never pass a workflow as ungated.

#### Scenario: Irreversible-capable action
- **WHEN** the imported workflow uses `file_delete`
- **THEN** no gym child process is created and the gym routes `escalate` with the reason

#### Scenario: Irreversible-capable construct action
- **WHEN** the imported workflow's top-level `construct_action` is `file_delete`
- **THEN** no gym child process is created, the gym routes `escalate`, and the owner's review
  lists `file_delete` flagged

#### Scenario: No golden tasks
- **WHEN** neither the offer nor the library has golden tasks for the workflow
- **THEN** the gym routes `escalate`

#### Scenario: Scored below the pass mark
- **WHEN** the candidate's mean score is below `pass_score`
- **THEN** the gym routes `rejected` with the scores and nothing is saved

### Requirement: Supervised pre-run approval
`check_launch` SHALL treat a library workflow whose `commons.supervised` is set as needing
approval, whatever the entry point (goal, agent loop, direct run, routine, `subworkflow`,
`parallel_subworkflows`, `llm_agent` tool). The launch SHALL then create a *Supervised run*
process whose first task is an owner-only human task "Run imported workflow X for this goal?"
listing every action the workflow runs (including construct / destruct actions) and flagging
those that are not always reversible; nothing of the imported workflow SHALL run before it is
approved. No workflow name SHALL exempt a supervised workflow from this check.

#### Scenario: Workflow named like the wrapper
- **WHEN** a supervised library workflow is named `Supervised run: X`
- **THEN** its launch still raises the pre-run approval

#### Scenario: First goal run of an imported workflow
- **WHEN** a goal selects a supervised workflow
- **THEN** the goal parks on the pre-run approval task and the workflow has no process yet

#### Scenario: Routine start
- **WHEN** a scheduled routine starts a supervised workflow
- **THEN** the same pre-run approval task is raised

#### Scenario: Owner rejects a goal's run
- **WHEN** the owner rejects the pre-run approval of a goal's workflow
- **THEN** the goal selects again without that workflow

#### Scenario: Flag clears
- **WHEN** a supervised workflow completes `SUPERVISED_RUNS` (3) approved runs successfully, or
  the owner clears it
- **THEN** its `commons.supervised` is false and later launches need no approval

### Requirement: Owner-only approvals and stop conditions
Tasks marked `owner_only` SHALL be completable only by the Commons owner. While the Commons is
off or the kill switch is on, imports, adoption and supervised launches SHALL be refused. The
emergency override SHALL set `supervised` again on every adopted workflow.

#### Scenario: Another user tries to approve
- **WHEN** a user who is not the owner submits an owner-only task
- **THEN** the submission is refused with 403 and the task stays ready

#### Scenario: Kill switch
- **WHEN** the kill switch is on and a supervised workflow is launched
- **THEN** the launch is refused

### Requirement: Commons plumbing runs only in its own workflows
`commons_adopt` SHALL adopt only when its process runs the shipped *Commons Import* workflow
(same tasks, routings and hooks) and the step journal records the judge (`proceed`) and the
personal-data scan (`clean`), plus ethics, the gym (`passed`) and the `sharing` trust gate
(`proceed`) when no owner approved, or the owner's `adopt` written by completing
`owner_approval`. `commons_supervised_run` SHALL start a workflow only when its process runs
the wrapper regenerated from that workflow's definition, the actions and summary the owner was
shown match it, and the journal records `approve_run` completed with `decision: run`. Neither
SHALL trust a process property for a gate or an approval. Imported and generated workflows
SHALL NOT use the Commons-internal actions.

#### Scenario: Forged supervised run
- **WHEN** an ordinary workflow writes `__supervised_launch__` and `__task_output_approve_run`
  itself and then runs `commons_supervised_run`
- **THEN** the task fails, nothing of the supervised workflow runs and no approved run is counted

#### Scenario: Direct adoption
- **WHEN** a workflow other than *Commons Import* runs `commons_adopt` with a validly signed file
- **THEN** the task fails and nothing is saved

#### Scenario: Commons Import started past its gates
- **WHEN** *Commons Import* is started at `adopt` with a forged offer
- **THEN** the import is rejected at stage `adopt` with "no record that judge passed" and nothing is saved

#### Scenario: Imported workflow uses commons_adopt
- **WHEN** an imported file's workflow uses a Commons-internal action
- **THEN** the judge rejects it with the action named

# self-improvement-workflow Specification

## Purpose
Let Zebra deliver changes to its own code through its development process: a GitLab issue goes
through Claude Code builder stages and Zebra's own reviews to one human review of the GitHub PR.

## Requirements

### Requirement: Improve Zebra drives the builder's delivery stages for an issue
The *Improve Zebra* workflow SHALL take a GitLab issue number and run the builder's `propose`
stage and then its `ship` stage on the branch `f<issue>/improve-zebra`, waiting for each on an
external builder task. Between them Zebra SHALL review the proposed outcomes against its own
source, and the ship stage's prompt SHALL carry the OpenSpec change name and that feedback. A
stage that does not finish (`failed`, `over_budget`, `rejected`, `cancelled`) SHALL fail the
process with the stage's error.

#### Scenario: Issue to PR review
- **WHEN** Improve Zebra starts for issue 251 and the builder finishes both stages
- **THEN** the spool received a `propose` and then a `ship` job for `f251/improve-zebra`, and
  the process waits on the PR review task

#### Scenario: Stage does not finish
- **WHEN** the propose or ship result state is `over_budget`
- **THEN** the process ends FAILED with that stage's error and no later stage is started

### Requirement: Zebra recommends from host-checked facts
After the ship stage Zebra SHALL judge each agreed outcome (met, partial, missed) and recommend
`merge`, `changes` or `reject`, using the PR, the pipeline status, the changed and sensitive files
and the branch diff from the builder's result. It SHALL NOT recommend `merge` when the pipeline
status is not `success`.

#### Scenario: Recommendation inputs
- **WHEN** the ship result reports pipeline `success`, sensitive file `scripts/x.sh` and a diff
- **THEN** the recommendation step is given all three with the outcomes, and its JSON answer is
  stored as `recommendation`

### Requirement: One human review of the pull request
The workflow SHALL have exactly one human task, `review_pr`, showing the PR link, the pipeline
status and link, the sensitive files, Zebra's recommendation and its outcome feedback, with routes
`merge`, `changes` and `reject`. `changes` SHALL run the ship stage again on the same branch with
the reviewer's feedback in its prompt; `reject` SHALL end the workflow without another stage.

#### Scenario: Changes requested
- **WHEN** the reviewer chooses `changes` with feedback "Rename flag()"
- **THEN** a new `ship` job for the same branch carries "Rename flag()" and the PR is reviewed again

#### Scenario: Rejected
- **WHEN** the reviewer chooses `reject`
- **THEN** the process completes and no further builder job is written

### Requirement: The dream cycle leaves system workflows alone
Every workflow tagged `system` SHALL be treated as internal, like the core system workflows: it
SHALL NOT be loaded for the dream cycle's optimizer and SHALL NOT be retired by the curator. The
optimizer SHALL reject a generated workflow whose name belongs to a system workflow, and SHALL
NOT save it.

#### Scenario: Tagged workflow not offered for optimization
- **WHEN** the library holds *Improve Zebra* (tagged `system`) and *Answer Question*
- **THEN** `load_workflow_definitions` returns only *Answer Question*

#### Scenario: Shadowing a system workflow
- **WHEN** the optimizer generates a new workflow named "Improve Zebra"
- **THEN** the change is recorded as failed ("system workflow") and no file is written

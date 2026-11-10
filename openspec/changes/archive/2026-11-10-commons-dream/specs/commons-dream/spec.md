## ADDED Requirements

### Requirement: Off by default
The dream cycle's Commons step SHALL do nothing but record `status: off` ("Commons off") when no
Commons publisher is configured (`ZEBRA_COMMONS_RELAYS` unset) or `COMMONS_DREAM_ENABLED` is
false, and `status: stopped` when the Commons is stopped. It SHALL never fail the dream cycle.

#### Scenario: Relays unset
- **WHEN** the dream cycle runs without a Commons publisher
- **THEN** the step's output is `status: off` with a "Commons off" voice line, no process is
  started, no store is written and the cycle completes

#### Scenario: Unexpected error
- **WHEN** a store raises inside the step
- **THEN** the step completes with `status: error` and the message, and the cycle continues

### Requirement: Offer proposals
The step SHALL start *Commons Offer* for learnt, non-system workflows with at least
`MIN_RUNS_TO_OFFER` runs, a success rate and (when rated) a rating at or above the thresholds, that
pass `offer_refusal`, are not already offered, have no open *Commons Offer* and have not been
decided for `public` at this version, at most `MAX_OFFERS_PER_CYCLE` per cycle. A version already
`public` in `share_with` SHALL be offered again only while its latest `public` decision is none or a
plain approval, so the owner is asked about it once per version. It SHALL NOT approve, add `public`
to `share_with` or publish by itself.

#### Scenario: Good learnt workflow
- **WHEN** a learnt workflow has 6 successful runs rated 5 and passes every precondition
- **THEN** one *Commons Offer* is started and parks on the owner's approval, and `share_with` is
  unchanged

#### Scenario: Skipped workflows
- **WHEN** a workflow is a system or built-in workflow, adopted, leak-tainted, below the stats, or
  already offered
- **THEN** no offer starts for it and the report gives the reason

#### Scenario: Already public, then declined or blocked
- **WHEN** a version has `public` in `share_with` and its latest `public` decision is a decline or
  a refused publish (`blocked`)
- **THEN** no new *Commons Offer* starts for it on later cycles

#### Scenario: Cap
- **WHEN** two workflows qualify and the cap is 1
- **THEN** one offer starts and the other is skipped as over the cap

### Requirement: Import proposals
The step SHALL match capability gaps (creator-written workflows in the window, `new_workflow`
continuations) against `seen` offers by keyword overlap and start *Commons Import* only for offers
whose import score is at least `IMPORT_SCORE_THRESHOLD`, at most `MAX_IMPORTS_PER_CYCLE` per cycle,
and only while today's spend of dream-started imports is below `DAILY_IMPORT_BUDGET_USD`.

#### Scenario: Trusted matching offer
- **WHEN** a capability gap matches a seen offer whose score is 0.56
- **THEN** a *Commons Import* starts on it and the offer moves to `judging`

#### Scenario: Untrusted matching offer
- **WHEN** a capability gap matches a seen offer whose score is below 0.5
- **THEN** no import starts and the report gives the score as the reason

#### Scenario: Budget spent
- **WHEN** today's dream-started imports have spent the daily import budget
- **THEN** no import starts and the report says the budget is used

### Requirement: Sharing promotion request
The step SHALL queue a pending `sharing` trust suggestion one level up, with the counts as
evidence (approvals in a row, all decisions and the declines among them), once the owner's last
`COMMONS_SHARING_PROMOTION_APPROVALS` sharing decisions since the last `sharing` suggestion or level
change were approvals without a note (a decline or a note restarts the count). It SHALL NOT
queue one while a `sharing` suggestion is pending, at AUTONOMOUS, or set a trust level.

#### Scenario: Enough unchanged approvals
- **WHEN** the owner approved 5 share decisions without a note since the last sharing change
- **THEN** a pending `sharing` suggestion to SEMI_AUTONOMOUS is queued and the level is unchanged

#### Scenario: A decline resets
- **WHEN** the owner declined a share after 4 approvals
- **THEN** no suggestion is queued

#### Scenario: Evidence reports an earlier decline
- **WHEN** the owner declined one share and then approved 5 without a note
- **THEN** the suggestion's evidence says 6 decided in all, 1 declined

### Requirement: Commons report
The step SHALL write a `commons` report (status, offers proposed, imports started, skipped with
reasons, budget used, promotion) with first-person voice lines, which the dream-cycle summary and
the `/dreams/` page show.

#### Scenario: Dreams page
- **WHEN** a dream cycle has a `commons` report
- **THEN** `/dreams/` shows a Commons block with its voice lines and counts

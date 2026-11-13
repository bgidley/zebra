## MODIFIED Requirements

### Requirement: Ruling form is readable
The `human_ruling` form SHALL be generated per review (`review_result.ruling_form`). It SHALL list
the agreed outcomes in one line and give each disputed outcome its own read-only section (outcome
text, the crux when briefed, both verdicts each with a one-sentence position, and what would settle
it), immediately followed by that outcome's pick. The full evidence of every disputed outcome SHALL
stay on the page as the last panel. It SHALL NOT show earlier tasks' raw outputs, and reviewer or
brief text SHALL NOT be resolved as `{{templates}}`. The evidence table posted on the issue
(`table_markdown`) SHALL keep both reviewers' evidence.

#### Scenario: One outcome disputed
- **WHEN** the reviews disagree only on O5
- **THEN** the form has `agreed` listing the others, then `O5_case`, `O5` and `O5_note`, then `notes` and `evidence`, and `dispute_notes` has one section for O5 with both reviewers' evidence

#### Scenario: Summary has no evidence
- **WHEN** the reviews are compared
- **THEN** `summary_markdown` has one row per outcome with id, outcome text, Zebra's verdict, Claude's verdict and agreed, and no evidence

#### Scenario: Ruling page hides prior outputs
- **WHEN** the human opens the `human_ruling` task page
- **THEN** no earlier task output is shown above the form

#### Scenario: Reviewer text holds a template
- **WHEN** a reviewer's evidence contains `{{__secret__}}`
- **THEN** the form shows it literally (as `{ {__secret__} }`) and resolves nothing

#### Scenario: Narrow screen
- **WHEN** the ruling page is opened at 390px or 1280px wide
- **THEN** the page does not scroll sideways

## ADDED Requirements

### Requirement: Disputes are briefed without taking a side
When the reviews still disagree after reconsidering, `brief_outcome_disputes` SHALL make one
low-tier LLM call over both reviewers' evidence for the disputed outcomes only, and store per
outcome a crux, each side's position, and what would settle it in `review_result.briefs`. A brief
field that recommends a verdict or says which reviewer is right SHALL be dropped, and a brief
without a crux SHALL be dropped whole. The action SHALL never fail: without a brief the form shows
the first sentence of each side's evidence. The form SHALL label a brief as a model summary, not a
verdict.

#### Scenario: Brief succeeds
- **WHEN** the model returns a crux for O2
- **THEN** O2's section shows "In dispute:" with that crux, both positions and what would settle it

#### Scenario: Brief takes a side
- **WHEN** a brief field says "Zebra is right" or "this should be partial"
- **THEN** that field is dropped, and the brief is dropped if it was the crux

#### Scenario: Brief unavailable
- **WHEN** there is no LLM, the call raises, or the reply has no usable brief
- **THEN** the task succeeds with an `error`, `briefs` is empty, and the form still asks for a ruling

#### Scenario: Reviewers agree
- **WHEN** the reviews agree on the first or second comparison
- **THEN** no brief call is made

### Requirement: The human rules each disputed outcome
The ruling form SHALL have one required met / partial / missed pick per disputed outcome, labelled
with who gave each verdict ("Partial (Zebra)", "Met (Claude)", plain "Missed"), and an optional
note. On submission `review_result` SHALL record each pick as that row's `ruling` (and
`ruling_note`), add ruled partial or missed outcomes to `followups`, write `ruling` as one line per
outcome, list disputed outcomes without a pick in `unruled`, and add a Ruling column to
`table_markdown`. `zebra-outcome-review.sh` SHALL ask the session to read the ruling only for
`unruled` outcomes.

#### Scenario: Submission without a pick
- **WHEN** the human submits without choosing a verdict for a disputed outcome
- **THEN** the submission is refused and the task stays READY

#### Scenario: Ruled partial
- **WHEN** the human picks partial for O1 with the note "no test"
- **THEN** the review completes `ruled`, `followups` contains O1, `ruling` is "O1: partial: no test", and the issue table's Ruling column shows it

#### Scenario: No readable verdicts
- **WHEN** neither review could be read
- **THEN** the form asks for one free-text `ruling`, which is recorded as is with the outcomes `unruled`

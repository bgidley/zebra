## ADDED Requirements

### Requirement: Ruling form is readable
The `human_ruling` form SHALL show a compact per-outcome summary (id, outcome text, both verdicts,
agreed) and, for each disputed outcome only, its own section with the outcome text and each
reviewer's evidence. It SHALL NOT show earlier tasks' raw outputs. The evidence table posted on the
issue (`table_markdown`) SHALL keep both reviewers' evidence.

#### Scenario: One outcome disputed
- **WHEN** the reviews disagree only on O5
- **THEN** `dispute_notes` has one section, headed with O5 and both verdicts, holding O5's text and Zebra's and Claude's evidence as separate paragraphs

#### Scenario: Summary has no evidence
- **WHEN** the reviews are compared
- **THEN** `summary_markdown` has one row per outcome with id, outcome text, Zebra's verdict, Claude's verdict and agreed, and no evidence

#### Scenario: Ruling page hides prior outputs
- **WHEN** the human opens the `human_ruling` task page
- **THEN** no earlier task output is shown above the form

### Requirement: Human tasks can hide prior outputs
A human task whose properties set `show_prior_outputs: false` SHALL render its form without the
earlier tasks' outputs. Without the property, prior outputs SHALL be shown as before.

#### Scenario: Default names a field of a dict property
- **WHEN** a schema default is `{{review_result.dispute_notes}}` and `review_result` is a dict
- **THEN** the field shows `review_result["dispute_notes"]`

#### Scenario: Property unset
- **WHEN** a human task does not set `show_prior_outputs`
- **THEN** its page shows earlier tasks' outputs above the form

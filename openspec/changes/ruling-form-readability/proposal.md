## Why

The *Outcome Review — Your Ruling* form is hard to read (#215). On the #211 ruling it showed four
raw-JSON dumps of earlier steps (11–13 KB each) above the form, a six-column side-by-side table with
400–800 character evidence cells squeezed into a 42rem column, and the one disputed outcome as a
run-on sentence with both reviewers' evidence in parentheses. The human has to dig to find the one
thing they are asked to rule on.

Rendering it locally showed it was worse than cluttered: the comparison and dispute fields were
**empty**. Their defaults (`{{review_result.table_markdown}}`) are a field of a dict property,
and the form only resolved `{{key}}` and `{{task_id.output}}`. Prod's submitted ruling confirms it
(`comparison: ""`, `positions: ""`), so the human only had the raw JSON to go on.

## What Changes

- **Dotted defaults resolve**: a form `default` of `{{key.field}}` reads that field of a dict
  property.
- **Panels grow**: read-only markdown panels no longer cap at `max-h-96` with an inner scroll.

- **Summary table for the form**: `compare_outcome_reviews` also returns `summary_markdown`: one row
  per outcome with its id, its text from the outcomes table, both verdicts and whether they agree.
  No evidence. `table_markdown` (posted on the issue) is unchanged.
- **Readable dispute notes**: `dispute_notes` becomes one short markdown section per disputed
  outcome: a heading with both verdicts, the outcome text, then Zebra's and Claude's evidence as
  separate paragraphs. It still feeds Zebra's reconsider prompt.
- **Hide prior outputs**: a human task with `show_prior_outputs: false` does not show earlier tasks'
  outputs above its form. The ruling form sets it, since its own fields already show what matters.

## Non-goals

- The reconsider step returning garbage (#216).
- Restyling human task forms in general.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The ruling form shows no raw JSON | Test: a task with `show_prior_outputs: false` renders no earlier outputs or `<pre>` JSON while its own fields still show; other human tasks still show prior outputs |
| O2 | The disputed outcome is easy to find and read | Test: `dispute_notes` has a heading per disputed outcome naming both verdicts, the outcome text, and each side's evidence in its own paragraph; agreed outcomes are not in it. Browser render of the #211 ruling at desktop and phone width shows each section without clipping |
| O3 | The comparison fits the form | Test: the form's comparison shows id, outcome, both verdicts and agreed per outcome, no evidence; the browser render has no horizontal overflow at desktop width. The issue table (`table_markdown`, posted by `zebra-outcome-review.sh`) keeps the evidence |
| O4 | The ruling still works end to end | Workflow test: disputed → parked on `human_ruling` whose resolved form shows the summary and notes → submitted → `ruled` with the disputed ids. Rulings already parked keep their own definition version and render as before |

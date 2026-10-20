## Context

The ruling form (`outcome_review.yaml` `human_ruling`) shows three read-only markdown fields, and the
generic human task page shows every `__task_output_*` above any form. For the outcome review those
outputs are the full review JSON, rendered as `<pre>` blocks.

## Decisions

- **Separate summary, keep `table_markdown`.** The issue comment wants the evidence; the form does
  not have room for it. `summary_markdown` is the form's view, `dispute_notes` carries the evidence
  for the disputed outcomes only, where the human needs it.
- **Outcome text from the outcomes table.** `outcome_texts()` reads the second cell of each id row,
  like `outcome_ids()` reads the first. Missing text shows as `—`.
- **Opt-out property, not a new heuristic.** `show_prior_outputs: false` on the task definition is
  explicit and leaves every other human task as it is. Guessing (e.g. hide when the form has
  read-only fields) would change pages nobody complained about.

## Migration

None. A process stays on the definition version it started with, so a ruling parked on v3 keeps
`table_markdown` and its prior outputs; v4 applies to reviews started after deploy.

## Risks

- `dispute_notes` is also Zebra's reconsider input; markdown sections read as well as the old
  sentence form there.

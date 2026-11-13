## Context

*Outcome Review* (#190) parks on `human_ruling` when Zebra and Claude still disagree after one
reconsider round. Since #215 the form had three static fields (`comparison`, `positions`,
`ruling`) whose defaults point at `review_result`. Rulings on prod ran to 150+ words of evidence
per side and were answered with one line for several outcomes (#295).

## Decisions

**Generated schema, not static fields.** `human_ruling.schema` is
`"{{review_result.ruling_form}}"`, resolved by `zebra.forms.resolve_task_schema` (#179). The
form needs one pick per disputed outcome, and only code knows which outcomes those are.
`compare_outcome_reviews` always writes `ruling_form` (cheap and deterministic), and
`brief_outcome_disputes` rebuilds it with the cruxes.

**The brief is a separate never-failing action, not `llm_call`.** `llm_call` fails the task on any
provider error, which would fail the review on the human path. `brief_outcome_disputes` makes one
low-tier `complete_json` call and catches everything; without a brief each position falls back to
the first sentence of that side's evidence. It runs only on the still-disputed path, so the agreed
path costs nothing more.

**Neutrality is enforced on the output.** The prompt says not to judge, and `parse_briefs` drops any
field matching `TAKES_A_SIDE` ("Zebra is right", "should be partial", "correct verdict",
"I recommend …", "rule in favour …"). A brief without a crux is dropped whole. The form labels the
brief "Summary by a low-tier model, not a verdict", and the full evidence stays as the last panel.
Raw HTML is escaped by the markdown renderer, so there is no `<details>`: the evidence is an
ordinary panel after the picks.

**Template safety.** The web view resolves `{{…}}` in schema defaults and descriptions. Reviewer
and brief text is untrusted, so `_inert()` breaks every `{{` / `}}` before it goes into the form.

**Field names.** Per disputed outcome: `<id>_case` (read-only), `<id>` (select, required),
`<id>_note`; plus `agreed` (one line), `notes` and `evidence`. `field_key()` makes an id safe as a
form name. With no readable verdicts at all the form keeps one free-text `ruling` field.

**Recording.** `record_ruling()` sets `ruling` / `ruling_note` on each disputed row, adds ruled
partial or missed ids to `followups`, writes `ruling` as one line per outcome (plus `notes`), lists
`unruled` disputed ids, and redraws `table_markdown` with a Ruling column. A free-text answer
(`{"ruling": "..."}`, the v5 form or the no-verdicts form) is kept as `ruling` and its outcomes
stay `unruled`. `compare_outcome_reviews` carries `briefs` from the previous `review_result` so the
final result keeps them.

## Risks

- A low-tier model can still misstate a position without "taking a side". Mitigation: the label,
  the full evidence on the page, and the brief never replaces the verdicts shown.
- `TAKES_A_SIDE` is a phrase list; a paraphrase can pass it. It is a backstop, not the main control.

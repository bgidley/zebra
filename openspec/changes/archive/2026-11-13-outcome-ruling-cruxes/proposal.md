## Why

When Zebra and Claude still disagree after the reconsider round, the *Outcome Review — Your
Ruling* form (#215) shows a verdict table, then each side's full case, often 150+ words of
file:line citations each, and one free-text ruling box (#295). On the last three rulings:

- The point of disagreement was buried. #279 O2 is really "is `deploy/oci/main.tf:111-113`
  fmt-clean?", but the human had to diff two essays to find that.
- The rulings were "Zebra is right" and "Met", each covering several outcomes. `record_ruling`
  stores that text as is, so no outcome gets a ruled verdict and a ruled partial or missed
  outcome never becomes a follow-up.

## What Changes

- **Dispute brief**: a new `brief_outcome_disputes` action runs once, only when the reviews still
  disagree after the reconsider round. One low-tier LLM call reads both cases per disputed outcome
  and returns, without judging, the crux (the one point they differ on), each side's position in a
  sentence, and what would settle it. It never fails the review: with no LLM, an error or an
  unusable reply, the form falls back to each side's first sentence.
- **Generated ruling form**: `compare_outcome_reviews` writes `review_result.ruling_form`, a JSON
  Schema the `human_ruling` task renders (`schema: "{{review_result.ruling_form}}"`). Per disputed
  outcome it has a read-only section (outcome, crux, both verdicts with positions, what would
  settle it), then a required met / partial / missed picker whose labels say who said which, and
  an optional note. The agreed outcomes are listed in one line, and the full evidence moves to one
  panel at the end.
- **Per-outcome ruling**: `record_ruling` reads the picks into each row (`ruling`, `ruling_note`),
  `table_markdown` gains a Ruling column, `followups` adds ruled partial and missed outcomes, and
  `ruling` becomes a one-line-per-outcome summary that `zebra-outcome-review.sh` prints. A ruling
  already parked on the v5 form (free text) still records as before.

## Non-goals

- A rebuttal round for Claude inside the workflow.
- Changing how either side reviews, or the agreed path (no extra LLM call when they agree).
- Restyling human task forms in general.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The ruling form says what is in dispute | Test: for each disputed outcome the generated form has a section with the outcome text, the crux, both verdicts each with a one-sentence position, and what would settle it; agreed outcomes are one line, not sections; the full evidence stays on the page as the last panel. Browser render of the real #279 ruling at 1280px and 390px: no horizontal overflow, and each outcome's section is immediately followed by its own pick |
| O2 | The brief never takes a side and cannot block a review | Test: the brief prompt holds both sides' evidence for disputed outcomes only and says not to judge; it is one low-tier call, made only on the still-disputed path; a brief field that recommends a verdict or says who is right ("Zebra is right", "should be partial", "I recommend …") is dropped (fixtures); the form labels the brief a model summary. No LLM, a raising call, garbage JSON or a missing id each still give a form (first-sentence fallback) and the workflow parks on `human_ruling` |
| O3 | The human rules each disputed outcome | Test: each disputed outcome has a required met / partial / missed select whose labels name who said which ("Partial (Zebra)", "Met (Claude)", unattributed "Missed"), plus an optional note; a submission without a pick is refused (`validate_form_data`, the web submit view, the browser) |
| O4 | The ruling is recorded per outcome and drives follow-ups | Workflow + web tests: submitting picks completes `ruled` with each row's `ruling`, a Ruling column in `table_markdown`, ruled partial/missed ids in `followups`, and a per-outcome `ruling` summary that `zebra-outcome-review.sh` prints without "Also check …" |

Zebra's feedback on the first draft (on the issue) asked for a pass/fail browser check, for the
evidence to stay reachable, and for neutrality to be checked on output, not just the prompt; O1 and
O2 now do. No v5 ruling is parked on prod, so v5 compatibility is not an outcome (the free-text
path stays for a review with no readable verdicts).

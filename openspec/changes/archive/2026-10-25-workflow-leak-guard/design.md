## Context

Design source: "Leak guard" in `specs/zebra-commons-design.md` and issue #237. The writers are
`WorkflowCreatorAction` (also behind `define_workflow`), `WorkflowVariantCreatorAction` and
`WorkflowOptimizerAction`. The optimizer only receives the evaluator's output, while the raw run
texts (sample failed goals, continuation comments) are in `metrics_analysis`, which only the
evaluator sees.

## Decisions

### Exposure set = the raw untrusted texts, not the evaluator's findings
The issue lists "evaluator findings" in the exposure set. Checking added text against the findings
would flag the optimizer for implementing a suggestion word for word, which is its job. Instead the
evaluator records the run texts it was shown (`evaluation.run_exposure`), and the optimizer checks
against those. Any specific the findings copied from a run is still in the run texts, so it is
still caught; anything the evaluator invented is not run content.

Per writer:

| Writer | Run texts (full check) | Goal texts (specifics + ≥ 8-token copies) | Parent | Allow |
|---|---|---|---|---|
| creator | previous-run context (`with_previous_run` minus the goal) | goal | — | system prompt + action list |
| variant creator | previous-run context | goal, selector reasoning | source YAML | system prompt |
| optimizer create | `evaluation.run_exposure` | — | — | system prompt + action list |
| optimizer modify | `evaluation.run_exposure` | — | current YAML | system prompt + action list |

### Two phrase lengths
A workflow made for a goal legitimately describes it ("plan a birthday party"). So the writer's
own goal is checked only for specifics and for long verbatim copies (≥ 8 tokens: a pasted goal),
while run content (other runs' goals, comments, outputs) gets 4-token phrases as the issue says.

### Detectors (on literals added versus the parent; `{{...}}` stripped first)
- **phrase**: n-gram of normalised tokens (lowercase, letters/digits) found in the exposure n-grams,
  not in the parent or allow text, with at least one informative token (not a stopword, not in the
  allow text). Overlapping windows merge into one reported phrase.
- **name**: a capitalised word in the exposure that is not sentence- or bullet-initial, at least 2
  characters, whose lowercase form is not a stopword or in the allow text; matched as a whole token
  case-insensitively (snake_case keys split, so `check_acme_sla` hits "Acme").
- **email**: an exposure email address appearing in a literal.
- **domain**: the host of an exposure URL or email domain (`www.` dropped) appearing in a literal.
- **number**: a digit run of ≥ 3 digits (separators `,` `.` removed) from the exposure.
Hits are deduplicated by (kind, text) and capped at 12 for reporting.

### Generalise once, then reject (dream cycle) or keep (user's goal)
`apply_guard(guard, yaml, regenerate, reject=)`: `LeakGuard.check(yaml)` → hits. The writer appends
its YAML and a generalise instruction listing the hits, regenerates exactly once (the creator path
reuses `generate_workflow`, which keeps its own validity retry), and checks again. An unusable
rewrite falls back to the first version and its hits.

- **Optimizer (`reject=True`)**: hits remain → `failed_changes` entry
  `{type, workflow, reason: "Leak guard: …", leak_hits}`; nothing saved or staged. Nobody asked for a
  dream-cycle change, so rejecting it loses nothing.
- **Creator / variant (`reject=False`)**: hits remain → the rewrite is kept with
  `leak_guard: {status: "kept", hits}`. The issue said reject, but a creator rejection fails the
  user's goal (the main loop has no fallback from `create_workflow`) over words the user wrote, and
  goals routinely name their topic ("Research the EU AI Act"). The design accepts that specifics can
  reach the library of the sphere that learnt them; the Commons layers (S3b scans, `tainted_by`,
  human diff review) guard anything leaving it, and they can read `kept`.
- A pass after regeneration records `leak_guard: {status: "generalised", hits}`.
- A crashing check: optimizer rejects (`status: rejected`, fails closed); creators keep the workflow
  with `status: error`.

### Acronyms are not names
A sample goal "fix the SLA alert" must not stop the optimizer writing "SLA". All-caps words are
skipped as names; an all-caps company name (IBM) is the accepted miss.

## Risks / Trade-offs

- Paraphrase beats it (accepted; see the Commons design's Risks).
- False positives regenerate a workflow (one extra LLM call). Names that are also common words
  ("Mark") can trigger it. The allow text (every word in the writer's prompt) removes technology
  words such as Python, JSON, Kagi.
- Sample goals are clipped to 100 chars by the analyzer, so the guard checks exactly what the
  evaluator saw, no more.

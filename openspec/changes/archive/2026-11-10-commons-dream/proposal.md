## Why

S4–S6 (#231, #232, #233) let the owner offer a learnt workflow, import another Zebra's offer and
weigh publishers by a web of trust, but every one of those starts by hand. This change (S8, GitLab
#235, epic #41) has the **dream cycle** propose them: Zebra suggests what to offer and which seen
offers to try for its capability gaps, and asks for more `sharing` autonomy once the owner keeps
approving its sharing proposals unchanged. Every proposal goes through the existing offer and
import workflows and their gates; nothing new can publish or adopt. Trades stay out (market parked,
#234). It ships **as code, off by default**: with `ZEBRA_COMMONS_RELAYS` unset the new step records
"Commons off" and does nothing else.

## What Changes

- **New dream-cycle step** `commons_dream` (`zebra_tasks/commons/dream.py`), wired into
  `dream_cycle.yaml` (v10) after `propose_improvements`, before the summary. It never fails the
  cycle: any error is recorded in its report.
- **Off / stopped**: no publisher (`ZEBRA_COMMONS_RELAYS` unset) or `COMMONS_DREAM_ENABLED` false →
  `status: off`, "Commons off"; the Commons stopped (off or kill switch) → `status: stopped`.
- **Offers**: learnt workflows (exportable, not an unmodified built-in, not adopted from another
  Zebra) with ≥ `MIN_RUNS_TO_OFFER` runs, success rate ≥ `COMMONS_OFFER_MIN_SUCCESS_RATE` and (when
  rated) average rating ≥ `COMMONS_OFFER_MIN_RATING`, passing `offer_refusal` (`commons_exportable`,
  `leak_kept`), not already offered, no *Commons Offer* already open for it and not already decided
  for this version. Each starts *Commons Offer* (the public suggest-and-approve step: it asks before
  `public` enters `share_with`, or publishes when it is already there), at most
  `MAX_OFFERS_PER_CYCLE` (1). The offer's own gates (scan, ethics, `sharing` trust gate / owner)
  decide; the step never approves.
- **Imports**: capability gaps = runs whose workflow the creator wrote because the selector found
  none (`creator` saves in the lineage journal in the window) plus continuations that reported
  `new_workflow`; matched against `seen` offers by keyword overlap over name, summary and use_when
  (the memory search's keyword ranking); kept only when the import score ≥
  `IMPORT_SCORE_THRESHOLD` (0.5). At most `MAX_IMPORTS_PER_CYCLE` (1) *Commons Import* runs start
  per cycle, in the background, while today's spend of dream-started imports (spend ledger over
  their process trees) is below `DAILY_IMPORT_BUDGET_USD`. An offer below the threshold is skipped
  with its score, never judged automatically.
- **Sharing promotion**: once the owner has approved `COMMONS_SHARING_PROMOTION_APPROVALS` (5)
  sharing decisions without a note, and declined none, since the last `sharing` suggestion or level
  change, the step queues a `sharing` promotion one level up via `propose_trust_promotion`'s
  `queue_promotion` (REQ-TRUST-004) with the evidence; never while one is pending; never self-sets.
- **Report**: `commons` output (status, offers proposed, imports started, skipped with reasons,
  budget used, promotion, voice lines in Zebra's own words); the summary prompt gets a Commons
  section and `/dreams/` shows a "Commons" block per cycle.
- **Settings** (env, task property overrides): `ZEBRA_COMMONS_DREAM_ENABLED` (true),
  `ZEBRA_COMMONS_MAX_OFFERS_PER_CYCLE` (1), `ZEBRA_COMMONS_MAX_IMPORTS_PER_CYCLE` (1),
  `ZEBRA_COMMONS_DAILY_IMPORT_BUDGET_USD` (0.50), `ZEBRA_COMMONS_OFFER_MIN_SUCCESS_RATE` (0.8),
  `ZEBRA_COMMONS_OFFER_MIN_RATING` (4.0), `ZEBRA_COMMONS_SHARING_PROMOTION_APPROVALS` (5).

## Capabilities

### New Capabilities
- `commons-dream`: the dream cycle's Commons step: off-by-default no-op, offer candidates and
  caps, import candidates (gaps, matching, score threshold, caps, daily budget), the `sharing`
  promotion request, the report and its `/dreams/` section.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With `ZEBRA_COMMONS_RELAYS` unset prod behaves as before: the dream cycle still completes, its new Commons step records "Commons off" and starts nothing, contacts no relay and makes no LLM call; an error inside the step (a raising store, an import that cannot start, an offer run that stops) never fails the cycle and is reported | Unit tests (off, disabled, stopped, raising store → `status: error`, import start failure → offer back to `seen`, offer run refused → skipped with its reason; task still ok); dream-cycle workflow test; prod `/dreams/` shows "Commons off" on the first cycle after deploy |
| O2 | A learnt workflow with ≥ 5 runs, success rate ≥ 0.8 and (when rated) average rating ≥ 4.0, that passes `offer_refusal` (exportable, `leak_kept` false) and is not offered, open or already asked about at this version, gets one *Commons Offer* per cycle that parks on the owner's approval; it is asked about once per version (journal `proposed`) and never twice while an offer is open; system, built-in, adopted, leak-tainted, low-stat workflows are skipped with a reason; the step itself publishes and approves nothing | Unit tests per filter, the cap and the once-per-version / open-offer dedupe; in-memory E2E: dream step → `owner_approval` human task in a *Commons Offer*, `share_with` unchanged, nothing on the relay, a second cycle starts no second offer |
| O3 | A capability gap with a matching seen offer from a trusted publisher (score ≥ 0.5) starts one *Commons Import* (offer → `judging`, so no later or concurrent cycle starts it again); an untrusted matching offer is skipped with its score and never judged; no import starts once today's (UTC) spend of dream-started imports, summed from the spend ledger over their process trees, reaches `DAILY_IMPORT_BUDGET_USD` (checked before each start, so one import may overrun by its own cost, bounded by the cap of 1) | Unit tests for matching, the 0.5 boundary, cap, budget (ledger sum, UTC day) and `judging` dedupe; in-memory E2E: trusted match → import process started, untrusted match → skipped with "score 0.00 < 0.50" |
| O4 | Zebra asks for more `sharing` autonomy only through a pending trust suggestion after 5 unchanged owner approvals in a row (approved with no note; a decline or a note restarts the count; autonomy approvals don't count) since the last `sharing` suggestion or level change, with the counts as evidence, never while one is pending and never by setting a level | Unit tests: threshold, decline / note reset, autonomy ignored, pending blocks, AUTONOMOUS asks nothing, trust level unchanged |
| O5 | The owner can see, per dream cycle, what Zebra did in the Commons in its own words, matching what it recorded: offers proposed, imports started, skipped with reasons, budget used | `/dreams/` page test renders the Commons block from a recorded report; summary prompt includes the Commons section; voice lines unit-tested against the recorded actions |

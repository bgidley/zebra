## Context

The Commons pieces exist: *Commons Offer* (`commons_offer.yaml`, S4) is the public
suggest-and-approve step (its approval adds `public` to `share_with`, then it publishes), *Commons
Import* (`commons_import.yaml` v2, S5) judges a seen `OFFER`, `CommonsExchange` keeps seen offers in
an `OfferStore`, and `WebOfTrust` / `offer_score` give the import score (S6). All are started by
hand. The dream cycle (`dream_cycle.yaml`) already ends with steps that start processes for human
review (`propose_zebra_improvements`).

## Goals / Non-Goals

**Goals:** one dream-cycle step that proposes offers and imports through the existing workflows,
bounded by caps and a daily budget, asks for `sharing` promotion, reports in Zebra's voice, and is
a no-op without relays.

**Non-Goals:** trades or any market term (#234); new gates or new ways to publish / adopt; LLM
matching (keyword overlap only, so untrusted offer text never reaches a prompt); deploying or
switching the Commons on.

## Decisions

- **One action, `commons_dream`** (`zebra_tasks/commons/dream.py`), `context_dependent`, in
  `COMMONS_INTERNAL_ACTIONS` (no generated workflow may use it). It catches everything: on an
  unexpected error the output is `status: error` with the message and the task still succeeds.
- **Off** = no `__commons_publisher__` (only built with `ZEBRA_COMMONS_RELAYS`) or
  `COMMONS_DREAM_ENABLED` false. **Stopped** = `commons_stop_reason(extras)`. Neither reads stores.
- **Offers: (a) and (b) share one path.** *Commons Offer* is the existing suggest-and-approve flow:
  with `public` not yet in `share_with` its approval adds it; with `public` already there (approved
  earlier, not published) it publishes after its gates. The step starts it with
  `create_library_process(entry="dream_cycle")` and runs it inline until it parks on the owner (as
  `manage.py commons_offer` does). The step records the kind (`suggest` / `publish`).
- **Offer filters**, in order, each a recorded skip reason: system / not exportable, unmodified
  built-in (`builtin_hashes`), adopted (`origin_pubkey`), stats (runs, success rate, rating — an
  unrated workflow passes the rating test), `offer_refusal` (exportable, `leak_kept`, runs),
  already offered (`publisher.offered_hashes`), a *Commons Offer* for it still open, the version
  already decided for `public` (journal `latest_decision` in `DECIDED`, only while `public` is not
  in `share_with`). Candidates are ordered by success rate, rating, runs. When it starts a suggest,
  it journals `proposed` for (hash, `public`), so each version is suggested once.
- **Gaps**: (1) `saved` journal records with `writer: creator` in the last `lookback_days` (7) —
  the selector found no good workflow, so the creator wrote one; the gap text is that workflow's
  name, description and use_when; (2) `metrics_analysis.continuation_analysis.capability_gaps`
  (`new_workflow` continuations): comment and rationale. Gaps stay local.
- **Matching**: `search_keywords` (the memory search's keyword split) on the gap; an offer matches
  when its name + summary + use_when share ≥ 2 keywords with it. Offers considered: status `seen`.
- **Score**: reports from the mirror's verified `ATTEST`s (`attestation_summary`), trust map from
  `exchange.trust` (none → empty → score 0), `offer_score`. Below `IMPORT_SCORE_THRESHOLD` →
  skipped with the score. Above: ordered by score then overlap.
- **Import start**: `exchange.begin_import(sha)` → `create_library_process(Commons Import,
  entry="dream_cycle", properties={offer_event, goal, __user_id__ owner, __commons_dream_import__:
  true})` → `engine.start_process` in a background task (the gym is long); a failure to create
  calls `abandon_import`. Imports are judged and adopted only by the import workflow's gates.
- **Budget**: today (UTC) = processes of the *Commons Import* definition created since 00:00 UTC
  with `__commons_dream_import__`; spent = `metrics.get_spend_for_processes(run_process_ids(...))`,
  else the sum of their `__total_cost__`. No import starts once spent ≥ `DAILY_IMPORT_BUDGET_USD`.
  The budget is checked before each start, so one import may overrun it by its own cost.
- **Promotion**: owner from `library.refresh_owner()`; level from `__trust_store__`. Window starts
  at the newest `sharing` suggestion (any status) or level change. In the window, share journal
  records (any sphere) count: `approved` with no note (reason empty or "approved by the owner") is
  an unchanged owner approval; `declined` or an approval with a note resets the count; autonomy
  approvals ("approved by earned sharing autonomy") do not count. At the threshold it queues
  SUPERVISED → SEMI_AUTONOMOUS or SEMI → AUTONOMOUS via `queue_promotion` (factored out of
  `ProposeTrustPromotionAction`, the only trust write path), never while a `sharing` suggestion is
  pending. Like everything else in the step, only when it is on (relays set).
- **Report**: `commons = {status, voice: [..], offers_proposed, imports_started, skipped,
  budget: {limit, spent, remaining}, promotion, errors}`; voice lines are fixed first-person
  templates (no LLM). `generate_summary` gets a Commons section; `/dreams/` shows a Commons block.

## Risks / Trade-offs

- Keyword matching misses paraphrases → only fewer proposals, never an unsafe one.
- Budget overrun by one import's cost → bounded by the cap (1 per cycle).
- An offer run that fails before parking leaves a `proposed` record for that version; Zebra asks
  again for the next version. Acceptable: no repeated nagging.

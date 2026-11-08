## Context

S4 (#231) built `OFFER` events, `CommonsPublisher` (`__commons_publisher__`), the append-only
mirror (`CommonsMirror`, `CommonsEventModel`) and the off-by-default wiring (`COMMONS_RELAYS`).
S3 (#230) built the judged import (`commons_import.yaml`) from a signed export file. This change
reads offers, imports from them and publishes `ATTEST`s, reusing all of that.

## Goals / Non-Goals

**Goals:** offer intake with full verification; one `WorkflowOfferModel` row per content hash;
owner-started import of an offer; signed attestations of import outcomes and later runs; the
`/commons/` offers section. Off unless `COMMONS_ENABLED` and `ZEBRA_COMMONS_RELAYS` are set.

**Non-Goals:** choosing import candidates or an import score (S6 / S8), trust weighting of
attestations (S6), `OUTCOME` / market (S7), public genealogy (#247), deletion (NIP-09) handling.

## Decisions

- **One service, `CommonsExchange`** (`zebra_agent/commons/exchange.py`), injected as
  `extras["__commons_exchange__"]` only when a publisher was built. It owns the publisher (to sign
  and publish), the mirror and an `OfferStore`. `poll()` (each daemon tick from `publish_tick`)
  does intake and attestation fetches; `record_import()` and `after_run()` attest. No exchange,
  nothing happens: that is the off switch.
- **Intake verifies everything before storing**: `verify_offer` with the publishers' certs and
  revokes fetched from the same relay and the operator's receipts (revocation order). Own offers
  are skipped (they show under "my offers"). A second `OFFER` with a stored hash is a duplicate and
  changes nothing; the row's own event (`event_id`) no longer verifying because its device was revoked delists a
  `seen` row; any other failing event with the same hash (a revoked third-party copy) changes nothing.
- **`OfferStore`** (`zebra_agent/commons/offers.py`) with `InMemoryOfferStore` and the web's
  `DjangoOfferStore` over `WorkflowOfferModel`. Transitions are a fixed table: `seen → judging |
  delisted`, `judging → adopted | rejected | seen | delisted`, `rejected → judging | delisted`,
  `adopted → delisted`. Anything else raises `InvalidOfferTransition`.
- **Import from an offer**: the run input `offer_event` is `{"event": OFFER, "chain": [certs,
  revokes]}` as JSON text. `offer_as_export()` verifies it (`verify_offer`, plus held certs and
  revokes) and returns the same `ExportVerification` the file path yields, with a synthesized
  received block (`content_sha256`, public `parent`, `origin_pubkey`, `foreign_users: false`).
  So the judge, gym, trust gate and `adopt_export` are unchanged; both judge and adopt re-verify.
  `commons_import.yaml` goes to version 2.
- **Attestation of an import** is a new last step, `commons_attest_import`, reached from every
  `record_*` step. It runs only in the shipped *Commons Import* (`guard.is_import_workflow`) and
  derives the label from the step journal: adopt routed `adopted` → `adopted`; `pii_scan` routed
  `rejected` → `pii-found` (findings) or `rejected-pii` (failed closed); `ethics` routed `reject` →
  `rejected-ethics`; `gym` routed `rejected` → `rejected-gym`. Judge rejections, an owner's "no"
  and adopt refusals are local and not about the workflow, so they update the offer row but are
  not attested. Only imports whose judge recorded `import_source.source == "offer"` attest: a
  privately shared file is never mentioned publicly, not even by hash. Never fails the workflow.
- **Run attestations**: `assess_and_record` passes only the workflow name and success flag to
  `exchange.after_run`. It attests only when the workflow's block is an adoption, the offer row
  for its hash is `adopted`, and the hash recomputed from the current YAML equals the block's and
  the offered hash. A locally modified copy has a new hash and never attests.
- **No personal data by construction**: `build_attest(label, sha, reason=, rating=)` takes no
  free text. `reason` must be in `REASONS[label]`; `rating` an int 1–5; tags are fixed (`L`, `l`,
  `x`, `zebra`, `t`, `v`). `verify_attest` refuses any other tag, key or reason.
- **Event shape**: kind 1232, tags `["L","zebra-commons"]`, `["l",label,"zebra-commons"]`,
  `["x",sha]`, `["zebra",zebra_pubkey]`, `t`, `v`; content `{"reason": ..., "rating"?: n}`. `x`
  is a single-letter tag, so readers filter by `#x` (`Filter.hashes`).
- **Publishing**: `CommonsPublisher.publish_event(event)` (extracted from `publish_offer`): certs
  first, canonical, local mirror, mirrors best effort, receipt wait.
- **Page counts**: from mirrored, verified `ATTEST`s; `adopted` / rejections count distinct
  attesting Zebras, `worked` / `failed` count events (trust weighting is S6). "From other Zebras"
  on my own offers excludes my own key.
- **Voice**: Zebra's reason for its judgement is a fixed first-person line per outcome, plus the
  gate's recorded reasoning (local only, never published) labelled as recorded reasoning.

## Risks / Trade-offs

- A `judging` row whose import process crashed stays `judging`; the owner cannot restart it from
  the page in S5. Mitigation: rare, visible on the page; S8 adds candidate management.
- A spammy Zebra can inflate `worked` counts; S6 weighs attestations by trust.
- Polling fetches every `OFFER` since the last poll (in memory; a restart re-reads, duplicates are
  cheap). A `limit` of 500 per poll bounds it.

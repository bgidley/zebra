> Branch: `f232/commons-attest`. Commit with `Refs #232` (do not close #232: the second-Zebra
> check in the runbook closes it).

## 1. Events and stores (zebra-agent, no Django)

- [x] 1.1 `commons/attest.py`: labels, reason vocabulary, `build_attest`, `verify_attest`
- [x] 1.2 `Filter.hashes` (`#x`)
- [x] 1.3 `commons/offers.py`: `OfferRecord`, statuses + transitions, `OfferStore` ABC, `InMemoryOfferStore`
- [x] 1.4 `offer.py` `offer_as_export()` (an `OFFER` as an `ExportVerification`)
- [x] 1.5 `CommonsPublisher.publish_event`; `publish_offer` uses it
- [x] 1.6 `commons/exchange.py` `CommonsExchange`: `poll`, `intake`, `record_import`, `after_run`, `attestation_summary`
- [x] 1.7 Tests: intake (bad sig, wrong cert, tampered YAML, duplicate, revoked → delisted, revoked third-party copy of the same hash leaves the row `seen`), transitions, attest build/verify, hash-equality rule

## 2. Import from an offer + attestation step

- [x] 2.1 `commons_judge_import` / `commons_adopt` accept `offer_event`; judge records `import_source`
- [x] 2.2 `commons_attest_import` (label from the journal; internal action; entry point)
- [x] 2.3 `commons_import.yaml` v2: `offer_event` input, attest step after every record step
- [x] 2.4 `assess_and_record` calls `__commons_exchange__.after_run(library, name, success)`
- [x] 2.5 Tests: two-Zebra in-memory E2E (offer → seen → import → adopted ATTEST → A's view → run → worked); no-personal-data test; file import never attests

## 3. Web (off by default)

- [x] 3.1 `WorkflowOfferModel` + migration; `DjangoOfferStore`
- [x] 3.2 `api/commons_exchange.py`: `build_commons_exchange`, tick from `publish_tick`, `start_offer_import`, `offers_overview`
- [x] 3.3 `/commons/` offers section + owner-only `POST /commons/offers/<sha>/import/`
- [x] 3.4 Tests: wiring off/on, model transitions, page (off, offers, owner-only)
- [x] 3.5 Playwright container check (phone width)

## 4. Integration + docs

- [x] 4.1 Gated podman strfry test: offer, attest, fetch by `#x`
- [x] 4.2 Runbook second-Zebra check; `zebra-commons-design.md`, `zebra-as-is.md`, AGENTS files

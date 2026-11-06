> Branch: `f231/commons-offers`. Commit with `Refs #231` (do not close #231: the manual check in
> the runbook closes it).

## 1. Kinds and hard filter

- [ ] 1.1 `commons/kinds.py`: fixed kinds, `PUBLIC_KINDS`; existing modules import from it
- [ ] 1.2 `CommonsClient.check_publish`: public relay → public kinds + `zebra-commons` tag only; `SKILL` private only
- [ ] 1.3 Tests: hard filter; write-policy kind numbers equal the table

## 2. OFFER and publisher

- [ ] 2.1 `commons/offer.py`: `build_offer`, `verify_offer`, `public_parent`, `MIN_RUNS_TO_OFFER`
- [ ] 2.2 `commons/mirror.py`: `CommonsMirror` ABC + `InMemoryCommonsMirror`
- [ ] 2.3 `commons/publisher.py`: `CommonsPublisher` (canonical + mirrors, certs first, receipts, mirror, observed spheres)
- [ ] 2.4 Tests: build/verify, tamper, parent privacy, publisher

## 3. Offer workflow

- [ ] 3.1 `zebra_tasks/commons/offer_actions.py`: `commons_prepare_offer`, `commons_offer_route`, `commons_offer_record`, `commons_publish`, `commons_record_offer`; entry points; guard list
- [ ] 3.2 `zebra-agent/workflows/commons_offer.yaml` (system)
- [ ] 3.3 Tests: each precondition refusal; observed taint; stale approval; E2E over the in-memory relay with the real write policy and receipt sidecar

## 4. Mirror model and wiring (off by default)

- [ ] 4.1 `CommonsEventModel` + migration 0034; `DjangoCommonsMirror`
- [ ] 4.2 Settings `COMMONS_RELAYS`, `COMMONS_RECEIPT_PUBKEY`; `api/commons_publish.py` `build_commons_publisher`; engine injection; `manage.py commons_offer`
- [ ] 4.3 Tests: unset → nothing; set → built; model append-only + `user_id`

## 5. Public relay infrastructure (not deployed)

- [ ] 5.1 `deploy/podman/commons-relay/`: strfry Quadlet, `strfry.conf`, `write_policy.py`, receipt sidecar Quadlet, network; `receipts --secret-env`
- [ ] 5.2 Policy unit tests; deploy job does not install them; optional podman integration test (`ZEBRA_COMMONS_RELAY_IT=1`)

## 6. Docs

- [ ] 6.1 Design doc: kind table fixed, "Offers (S4) as built", config
- [ ] 6.2 `specs/commons-public-relay-runbook.md` + `specs/AGENTS.md`; `specs/zebra-as-is.md`; AGENTS.md files

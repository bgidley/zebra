> Branch: `f231/commons-offers`. Commit with `Refs #231` (do not close #231: the manual check in
> the runbook closes it).

## 1. Kinds and hard filter

- [x] 1.1 `commons/kinds.py`: fixed kinds, `PUBLIC_KINDS`; existing modules import from it
- [x] 1.2 `CommonsClient.check_publish`: public relay → public kinds + `zebra-commons` tag only; `SKILL` private only
- [x] 1.3 Tests: hard filter; write-policy kind numbers equal the table

## 2. OFFER and publisher

- [x] 2.1 `commons/offer.py`: `build_offer`, `verify_offer`, `public_parent`, `MIN_RUNS_TO_OFFER`
- [x] 2.2 `commons/mirror.py`: `CommonsMirror` ABC + `InMemoryCommonsMirror`
- [x] 2.3 `commons/publisher.py`: `CommonsPublisher` (canonical + mirrors, certs first, receipts, mirror, observed spheres)
- [x] 2.4 Tests: build/verify, tamper, parent privacy, publisher

## 3. Offer workflow

- [x] 3.1 `zebra_tasks/commons/offer_actions.py`: `commons_prepare_offer`, `commons_offer_route`, `commons_offer_record`, `commons_publish`, `commons_record_offer`; entry points; guard list
- [x] 3.2 `zebra-agent/workflows/commons_offer.yaml` (system)
- [x] 3.3 Tests: each precondition refusal; observed taint; stale approval; E2E over the in-memory relay with the real write policy and receipt sidecar

## 4. Mirror model and wiring (off by default)

- [x] 4.1 `CommonsEventModel` + migration 0034; `DjangoCommonsMirror`
- [x] 4.2 Settings `COMMONS_RELAYS`, `COMMONS_RECEIPT_PUBKEY`; `api/commons_publish.py` `build_commons_publisher`, `publish_tick` (daemon: late receipts), `start_offer`; engine injection; `manage.py commons_offer`
- [x] 4.3 Tests: unset → nothing; set → built; model append-only + `user_id`

## 5. Public relay infrastructure (not deployed)

- [x] 5.1 `deploy/podman/commons-relay/`: strfry Quadlet, `strfry.conf`, `write_policy.py`, receipt sidecar Quadlet, network; `receipts --secret-env`
- [x] 5.2 Policy unit tests; deploy job does not install them; optional podman integration test (`ZEBRA_COMMONS_RELAY_IT=1` in CI; runs locally when podman and the image are there)

## 6. Docs

- [x] 6.1 Design doc: kind table fixed, "Offers (S4) as built", config
- [x] 6.2 `specs/commons-public-relay-runbook.md` + `specs/AGENTS.md`; `specs/zebra-as-is.md`; AGENTS.md files

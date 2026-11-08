## Why

S4 (#231) lets a Zebra publish `OFFER`s to the public Commons, but no Zebra reads them yet and
nobody learns what happened when a workflow was tried. This change (S5, GitLab #232, epic #41)
closes the loop **as code, off by default**: a Zebra subscribes to offers, its owner can start a
judged import of one, and it publishes signed `ATTEST`ations of the outcome (adopted or the
rejecting gate, then worked / failed after runs). With `ZEBRA_COMMONS_RELAYS` unset prod behaves
exactly as today: no subscription, no relay connection, no attestations.

## What Changes

- **Offer intake** (`zebra_agent/commons/exchange.py`): each daemon tick fetches `OFFER`s from the
  canonical public relay with the publishers' `DEVICE_CERT`s / `DEVICE_REVOKE`s and the operator's
  receipts, verifies signature, attribution and hash (`verify_offer`), mirrors them in
  `CommonsEventModel` and records each as a `WorkflowOfferModel` row (one per content hash,
  status `seen` / `judging` / `adopted` / `rejected` / `delisted`, `judgement` JSON, `user_id` =
  owner; new migration) behind an `OfferStore` interface. Nothing is imported automatically.
- **Import from an offer**: `commons_import.yaml` (version 2) accepts an `offer_event` (the
  `OFFER` and its certs) as well as an export file; the judge and the adopt step both re-verify it
  and its hash. The owner starts it with "Import this" on `/commons/`.
- **`ATTEST` events** (`zebra_agent/commons/attest.py`), NIP-32 style: `L`=`zebra-commons`,
  `l`=`adopted` / `rejected-ethics` / `rejected-gym` / `rejected-pii` / `pii-found` / `worked` /
  `failed`, `x`=sha256, `zebra`, content `{reason, rating?}` with `reason` from a fixed vocabulary.
  Signed by the device key, attributed by its `DEVICE_CERT`, published through `CommonsPublisher`
  with receipts, mirrored.
- **Automatic attestations**: a new last step of *Commons Import*, `commons_attest_import`, reads
  the outcome from the step journal (never a process property) and attests it, only for imports
  that came from a public `OFFER`. After a run of an adopted workflow `assess_and_record` asks the
  exchange to attest `worked` / `failed`, only while the local content hash equals the offered
  hash.
- **No personal data**: attestation content and tags are built from the label, the hash, the
  Zebra key and a fixed reason; goal text, outputs, names and LLM text never reach them.
- **`/commons/` page**: this Zebra's npub, offers seen (status, publisher npub / fingerprint,
  stats, worked / failed / rejected counts, Zebra's reason in its own voice), its own published
  offers with attestations from other Zebras, the owner's "Import this", empty states while
  publishing is off.
- **Runbook**: the second-Zebra manual check that closes #232.

## Capabilities

### New Capabilities
- `commons-attestations`: offer intake and `WorkflowOfferModel`, import from an offer, `ATTEST`
  build / verify, automatic attestations with the hash-equality and no-personal-data rules, the
  `/commons/` offers section, off-by-default wiring.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With `ZEBRA_COMMONS_RELAYS` unset (or the Commons off) prod behaves exactly as before: no exchange in the engine, no subscription or relay connection, no attestation, and `/commons/` shows empty offer states | Wiring unit tests (no `__commons_exchange__` unless Commons on + relays + identity; `publish_tick` no-op); page test with publishing off; prod logs after deploy show no Commons subscription |
| O2 | A second Zebra records a first Zebra's offer only if it verifies (signature, device cert, hash), once per content hash, and its owner can import it through the existing judged import | Unit tests for intake (bad sig, wrong cert, tampered YAML, duplicate hash) and status transitions; in-memory two-Zebra E2E: A offers, B sees it, B's owner approves the import, the workflow is adopted supervised |
| O3 | Every judged-import outcome of an offer and every later run of the adopted workflow produces a signed `ATTEST` that verifies as coming from the importer and shows on the publisher's `/commons/` page; a locally modified copy never attests | Two-Zebra E2E: B's `adopted` then `worked` attestations appear on the relay and in A's view; unit test for the hash-equality rule; optional podman strfry test |
| O4 | Attestations never carry goal text, outputs, names or anything about humans | Test feeding goal text, outputs and personal data into the run and asserting none of it is in any `ATTEST`'s content or tags; reasons from a fixed vocabulary only |
| O5 | The owner can run the two-Zebra check that closes #232 from the runbook alone, and `/commons/` is readable on a phone | `specs/commons-public-relay-runbook.md` second-Zebra section; Playwright container check at phone width; summary on #232 |

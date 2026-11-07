## Context

Design: `specs/zebra-commons-design.md` (Event kinds, Offer control flow, Infrastructure, hard
filter). On master: identity and certs (S1), provenance and export (S2), import (S3), skill sync
(S3b-1) and the real Nostr client, receipts sidecar and offline queue (#246). This slice reuses
`RelayCommonsClient`, `NostrSdkTransport`, `Outbox` and `ReceiptSigner` unchanged in shape.

## Goals / Non-Goals

**Goals:** fixed kind numbers; `OFFER` build and verify; the hard filter; the offer workflow with
fail-closed preconditions; a local mirror; off-by-default wiring; public relay files and runbook.

**Non-Goals:** subscribing to other Zebras' offers, `WorkflowOfferModel`, attestations (S5,
#232); trust edges (S6); the market (S7); dream-cycle proposals (S8, #235); a web button.

## Decisions

- **Kind numbers.** Keep the provisional numbers already in code (changing them would orphan
  certs stored by S1) and declare them final; new kinds follow the same scheme (the number ends
  in the slice that introduced it; addressable in 30000–39999, regular in 1000–9999), checked
  against the NIP kind registry for clashes. One table, `commons/kinds.py`; the relay write
  policies (stdlib only, inside strfry) repeat the numbers and a test keeps them equal.
- **Hard filter at the client.** `check_publish` refuses on a public client any kind outside
  `PUBLIC_KINDS` and any event without `["t","zebra-commons"]`; `SKILL` only on a private one.
  Every implementation calls it, so the publisher cannot skip it.
- **Parent privacy.** `parent` is the block's `parent_sha256` only if this Zebra's mirror holds an
  `OFFER` of that hash; otherwise no `parent` tag (not even a hash).
- **What is published is what was scanned.** `commons_publish` takes the offer from the step
  journal entry of `prepare` (engine-written), checks its YAML still hashes to the library's
  current `content_sha256`, and signs it. Like `commons_adopt` it runs only inside the shipped
  workflow and checks the journal for each gate.
- **`public` in `share_with`.** The offer workflow is the public suggest-and-approve step: its
  approval calls `library.approve_share(name, "public", hash)` and writes a `share` journal record
  (sphere `public`), as skill sync does for spheres. `commons_publish` refuses unless `public` is
  in the current version's `share_with`. Observed taint (a sphere in `tainted_by` that a cert marks
  observed, or one no cert describes) routes straight to the owner approval, never through
  `trust_gate`, so neither earned autonomy nor freeing skips it.
- **Summary is honest and leak-free.** One low-tier `complete_json` call sees only the YAML and the
  numeric stats (never run goals) and writes `summary`, `use_when` and 1–3 golden tasks; the PII
  scan then checks YAML and golden tasks. No LLM or a bad reply refuses the offer.
- **Mirror store.** `CommonsMirror` ABC in `zebra_agent` (in-memory for tests), Django
  implementation in the web app over `CommonsEventModel`. Append-only: `save()` of an existing row
  and `delete()` raise. Receipts are stored as their own rows; a row's `relay_seq` is set when the
  receipt is already known at insert.
- **Public relay.** A second strfry, separate network, volume and operator key, loopback port
  7779, no NIP-42; write policy accepts `zebra-commons` events of public kinds, refuses NIP-70
  protected events and receipts not from the operator; journals for receipts. The sidecar is
  `python -m zebra_agent.commons.receipts --secret-env ZEBRA_COMMONS_OPERATOR_SECRET`.

## Risks / Trade-offs

- An open public relay can be spammed; the write policy limits kinds and tags only. Rate limits
  are deferred (S5 sees real traffic first).
- `DEVICE_CERT`s on the public relay show the device label and sphere; the design says certs go
  to both relays. The runbook tells the owner to pick neutral labels.
- Receipts arrive asynchronously; `publish_offer` waits briefly, else the receipt is picked up
  later by `refresh_receipts()`.

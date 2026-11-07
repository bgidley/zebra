## Why

The Zebra Commons lets Zebras share learnt workflows. S1–S3b gave a Zebra an identity, signed
provenance, judged import and private skill sync between its own devices. Nothing can yet be
offered **publicly**: there is no `OFFER` event, no public relay, no local record of what was
published, and the event kind numbers are still provisional. This change (S4, GitLab #231, epic
#41) adds public offers **as code, off by default**. With `ZEBRA_COMMONS_RELAYS` unset prod
behaves exactly as today, and the public relay is in the repo but not installed by the deploy job.

## What Changes

- **Kind numbers fixed** (`zebra_agent/commons/kinds.py`, the one table): the existing provisional
  kinds become final (`DEVICE_CERT` 30228, `DEVICE_REVOKE` 1228, export 31229, `SKILL` 4236,
  `RECEIPT` 1246). New: `OFFER` 30231 (addressable, `d` = content hash), `ATTEST` 1232, `TRUST`
  30233 (addressable, `d` = target), `GRANT` 1234, `TRADE` 1235, `OUTCOME` 1236. `PUBLIC_KINDS`
  is the list a public relay may carry.
- **Hard filter** in `CommonsClient.check_publish`: a public relay gets only `PUBLIC_KINDS` events
  tagged `zebra-commons`; `SKILL` goes only to the private relay.
- **`OFFER` events** (`commons/offer.py`): `{name, summary, use_when, stats, actions,
  golden_tasks, yaml}`, tags `d`/`x` = sha256, `zebra`, `t`, `v`, and `parent` only when that
  parent was itself publicly offered by this Zebra. Signed by the device key, attributed through
  `DEVICE_CERT`. `verify_offer` checks shape, hash and attribution.
- **`CommonsPublisher`** (`commons/publisher.py`): publishes to the canonical relay (first of
  `ZEBRA_COMMONS_RELAYS`, receipts trusted from `ZEBRA_COMMONS_RECEIPT_PUBKEY`) and the mirrors;
  publishes the device's certs before an offer; looks up the receipt; records everything in the
  local mirror.
- **`CommonsEventModel`** + migration: an append-only local mirror of every Commons event this
  Zebra publishes or relies on (`event_id`, `kind`, `pubkey`, `created_at`, `relay_seq`, `content`
  JSON, `sig`, `user_id` = instance owner), behind a `CommonsMirror` store interface.
- **`commons_offer.yaml`** (system, protected): `commons_prepare_offer` → `commons_pii_scan` →
  `ethics_gate` (plan_review) → route → `trust_gate` (sharing) / owner approval →
  `commons_offer_record` → `commons_publish`. Preconditions fail closed with a recorded reason:
  `commons_exportable`, leak guard not kept/error, ≥ `MIN_RUNS_TO_OFFER` (5) runs, `public` in
  `share_with` at publish (set by this workflow's own suggest-and-approve step, through the same
  `approve_share` and `share` journal records as skill sync); observed taint always needs the
  owner, whatever the trust level or freeing.
- **Wiring**: `__commons_publisher__` is injected only when the Commons is on, relays are set and
  the device has an identity; `manage.py commons_offer NAME` starts an offer; each daemon tick
  fetches late receipts (`publish_tick`, nothing without a publisher).
- **Public relay infrastructure, not deployed**: `deploy/podman/commons-relay/` (strfry Quadlet on
  `127.0.0.1:7779`, config with no NIP-42, write policy accepting only `zebra-commons` events of
  public kinds and operator receipts, receipt sidecar reusing `zebra_agent.commons.receipts` with
  `--secret-env ZEBRA_COMMONS_OPERATOR_SECRET`).
- **Runbook** `specs/commons-public-relay-runbook.md`.

## Capabilities

### New Capabilities
- `commons-offers`: kind table, `OFFER` build/verify and parent privacy, the publisher and local
  mirror, the offer workflow and its preconditions, off-by-default wiring and the public relay.

### Modified Capabilities
- `commons-skill-sync`: the Commons client's hard filter also limits public relays to the public
  kinds.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With `ZEBRA_COMMONS_RELAYS` unset (or the Commons off) prod behaves exactly as before: no publisher in the engine, no relay connection, the deploy job installs no public relay unit | Wiring unit tests (no `__commons_publisher__` unless Commons on + relays + identity); test that `deploy-podman.sh` installs only `deploy/podman/quadlet/*.container` and no relay file is there; prod logs after deploy show no Commons publishing |
| O2 | Offering a workflow with ≥ 5 runs, once the owner approves, puts exactly one signed `OFFER` on the relay, with an operator receipt, that verifies as coming from this Zebra's npub | E2E over the in-memory relay with the real write policy and receipt sidecar; optional podman strfry test (skips cleanly) |
| O3 | Nothing private reaches a public relay: the hard filter refuses non-public kinds and `SKILL`; an `OFFER` never names a private parent; each precondition (not exportable, leak kept, < 5 runs, `public` not approved, observed taint without the owner) refuses with a recorded reason | Unit tests for the hard filter, parent rule and each refusal |
| O4 | Every Commons event this Zebra publishes is kept in an append-only local mirror owned by the instance owner | `CommonsEventModel` migration and model tests (insert, no update/delete, `user_id`) |
| O5 | The owner can bring the public relay up from the runbook alone | `specs/commons-public-relay-runbook.md` (Quadlets, proxy route, relays + receipt key, mirrors, the manual check that closes #231), summary on #231 |

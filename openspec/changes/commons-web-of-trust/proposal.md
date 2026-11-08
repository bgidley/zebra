## Why

S5 (#232) lets a Zebra see other Zebras' offers and attest what happened, but every publisher and
every attestation counts the same: a Sybil swarm can inflate `worked` counts and nothing tells the
owner whether an offer comes from a Zebra worth listening to. This change (S6, GitLab #233, epic
#41) adds a **weighted web of trust, computed locally by each Zebra**, and the **import score**
S8 will use to pick candidates. It ships **as code, off by default**: with `ZEBRA_COMMONS_RELAYS`
unset no `TRUST` event is published or fetched, and prod behaves exactly as today.

## What Changes

- **Stores** (`zebra_agent/commons/peers.py`): `PeerRecord` / `TrustEdge`, a `TrustStore` ABC and
  `InMemoryTrustStore`; the web's `DjangoPeerTrustStore` over new `PeerModel` (pubkey unique,
  `display_name`, `vouched_by_user`, `owner_weight`, `local_trust`, `best_path`, `last_seen`,
  `user_id` = owner) and `TrustEdgeModel` (latest edge per `(from_pubkey, to_pubkey)`: `weight`
  -1..1, `reason`, `event_id`, `created_at`, `relay_seq`, `published_weight`); one migration.
- **`TRUST` events** (`zebra_agent/commons/trust.py`): kind 30233, addressable, `d` = `p` = target
  Zebra, `zebra` = the trusting Zebra, content `{reason, weight}`; signed by a certified device key
  (like `ATTEST`), `build_trust` / `verify_trust`. Published through `CommonsPublisher` with
  receipts, mirrored; fetched from the canonical relay each daemon tick and stored as edges, the
  latest per pair by receipt order, else `created_at`.
- **Human vouching**: owner-only "I know this Zebra" on `/commons/` (on a peer, or by npub) sets
  `vouched_by_user` and publishes `TRUST` weight 0.8; the owner can withdraw (0) or distrust
  (-0.8). The reason is a fixed word or the owner's own short note. No LLM ever sets trust.
- **Experience**: an EWMA over this Zebra's own `ATTEST`s about a publisher's workflows (`worked`
  raises; `failed`, `rejected-ethics`, `rejected-gym`, `pii-found` lower) updates this Zebra's edge
  to that publisher; it is published only when it moved by at least 0.1 since the last published
  weight. The owner's vouch is a floor (and a distrust a ceiling) the EWMA cannot cross.
- **Transitive local trust**: `t(me→Z) = max over paths p of ∏ weights × 0.9^(hops-1)`, at most 3
  hops, every path starting at a human-vouched seed, negative edges only as the last hop, this
  Zebra's own negative edge winning; deterministic; recomputed when edges change. No path from a
  vouched seed means 0 (Sybil limit). The best path is shown ("B via A: 0.8 × 0.6 × 0.9").
- **Import score**: `α·local_trust(publisher) + γ·attestation_signal` (α 0.7, γ 0.3, β = 0 while
  the market is parked); `attestation_signal` = trust-weighted mean of `worked` (+1) minus
  `failed` (-1) from other Zebras' `ATTEST`s. `IMPORT_SCORE_THRESHOLD` 0.5: below it an offer is
  never judged automatically (S8) and **Import this** shows the score with a warning.
- **`/commons/` peers section**: peers, local trust, vouch state, best path, edges in and out,
  Zebra's reasoning in its own voice, owner actions, empty states, phone layout checked.
- **Runbook**: the live check that closes #233.

## Capabilities

### New Capabilities
- `commons-web-of-trust`: `TRUST` build / verify, peer and edge stores, human vouching, experience
  EWMA with the vouch floor, transitive local trust with the Sybil limit, import score, the
  `/commons/` peers section, off-by-default wiring.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With `ZEBRA_COMMONS_RELAYS` unset (or the Commons off) prod behaves exactly as before: no `TRUST` is published or fetched, no relay is contacted, and `/commons/` shows the peers section's empty state | Wiring tests (no trust fetch or publish without the exchange; vouching with publishing off stores locally and publishes nothing); page test with publishing off; `podman logs zebra-web` for the hour after deploy has no `Commons:` TRUST lines |
| O2 | Local trust follows the defined formula: the owner vouches A (edge 0.8) and A trusts B (edge 0.6) gives B = 0.8 × 0.6 × 0.9 = 0.432; a third hop C (0.5) gives 0.8 × 0.6 × 0.5 × 0.81 = 0.194; it is the max over paths, a fourth hop gives 0, a negative edge is only ever the last hop. A cluster no human-vouched seed reaches gets 0 however much its members trust or attest each other | Unit tests per rule with these numbers, determinism and the best-path text ("B via A: 0.8 × 0.6 × 0.9 = 0.43"); in-memory multi-Zebra E2E: the owner vouches A, A trusts B, B's trust and the path show on `/commons/` |
| O3 | This Zebra's own edges change only by the owner (vouch 0.8 / withdraw 0 / distrust -0.8) or by its own attestations (EWMA rate 0.2: worked +1; failed, rejected-ethics, rejected-gym, pii-found -1), publish a signed `TRUST` only on a change of 0.1 or more, and never drop below the owner's vouch; other Zebras' edges enter only as `TRUST` events that verify, the latest per pair winning | Unit tests for `build_trust` / `verify_trust` (tampering, wrong cert, bad weight, extra tags, self-trust), EWMA values, publish threshold, vouch floor, latest-wins; no LLM call in any trust path |
| O4 | Every offer carries an import score `0.7·local_trust + 0.3·signal` (signal: trust-weighted mean of other Zebras' worked +1 / failed -1, publisher and this Zebra excluded); a score below 0.5 is flagged (exactly 0.5 clears), and an offer from an unconnected Zebra scores 0 and is flagged before the owner imports it | Unit tests for the score and the 0.5 boundary; E2E and page test: unconnected offer scores 0 with the warning |
| O5 | The owner can run the live check that closes #233 from the runbook alone, and the peers section works at phone width (390 px: no horizontal scroll, owner actions reachable) | `specs/commons-public-relay-runbook.md` web-of-trust section; Playwright container check at 390 px recorded in tasks.md; summary on #233 |

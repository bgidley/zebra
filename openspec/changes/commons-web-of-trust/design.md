## Context

S4 (#231) built the publisher, the append-only mirror and `TRUST_KIND` 30233 in the kind table. S5
(#232) built `CommonsExchange` (offer intake, `ATTEST`s, `/commons/` offers section). This change
adds trust edges, vouching, experience, local trust and the import score on top, reusing all of it.

## Goals / Non-Goals

**Goals:** `TRUST` events; peer and edge stores; owner vouching; experience EWMA; deterministic
transitive local trust with the Sybil limit; the import score and its warning; the `/commons/`
peers section. Off unless `COMMONS_ENABLED` and `ZEBRA_COMMONS_RELAYS` are set (local trust from
held edges is still computed).

**Non-Goals:** choosing import candidates automatically (S8 uses the score), the market term
(S7, parked: β = 0), encrypting edges, `GRANT` vouch-and-stake, public genealogy (#247).

## Decisions

- **Event** (`commons/trust.py`): kind 30233, tags exactly `["d",target]`, `["p",target]`,
  `["zebra",from]`, `t`, `v`; content `{"reason": r, "weight": w}` (sorted keys, `w` rounded to 2
  places, -1..1). Signed by a certified device key and attributed by its `DEVICE_CERT`
  (`verify_attributed`, receipt-ordered revocation), like `ATTEST`: devices do not hold the Zebra
  key. `reason` is a fixed word (`vouched`, `withdrawn`, `distrusted`, `experience`) or the
  owner's own note (1–140 printable characters, one line, published as typed). A Zebra cannot
  trust itself.
- **Latest wins** (`peers.is_newer`): per `(from, to)` an incoming edge replaces the stored one
  when both have a receipt `seq` and its `seq` is higher, otherwise when its `created_at` is later
  (ties: higher event id). Several devices of one Zebra can each have an addressable event for the
  same target; this rule picks one.
- **Stores** (`commons/peers.py`): `TrustStore` ABC with `InMemoryTrustStore`; the web's
  `DjangoPeerTrustStore`. `PeerRecord`: `pubkey`, `display_name`, `vouched_by_user`,
  `owner_weight` (what the owner set: 0.8 / -0.8 / None), `local_trust`, `best_path`,
  `last_seen`. `TrustEdge`: `from_pubkey`, `to_pubkey`, `weight`, `reason`, `event_id`,
  `created_at`, `relay_seq`, `published_weight` (the weight of this Zebra's last published
  `TRUST`; differs from `weight` while an experience change is below the threshold).
- **Service** `WebOfTrust` (`commons/web_of_trust.py`): owns the store, this Zebra's key and an
  optional `CommonsPublisher`. No publisher (relays unset): every change is local only; nothing
  is fetched. `vouch` / `withdraw` / `distrust` (owner only, from the web view) set the owner
  weight, the edge and publish at once. `record_experience(publisher, label)` is called by
  `CommonsExchange.attest` after each of this Zebra's own attestations.
- **Experience EWMA**: signal +1 for `worked`, -1 for `failed`, `rejected-ethics`,
  `rejected-gym`, `pii-found` (`adopted` and `rejected-pii`, a scan failing closed, say nothing
  about the publisher). `w' = (1-0.2)·w + 0.2·signal`, starting from the current edge (0 if none),
  then clamped to `[owner_weight, 1]` when vouched and `[-1, owner_weight]` when distrusted.
  Published when `|w' - published_weight| >= 0.1` (or never published); `publish_pending()` on
  each tick retries unpublished changes.
- **Local trust** (`trust.compute_trust(me, edges, seeds)`): enumerate simple paths from `me` of
  1–3 edges whose first edge goes to a human-vouched seed; interior edges must be positive (a
  negative edge is only ever the last hop). Value `∏ weights × 0.9^(hops-1)`, so a direct vouch
  is 0.8 and "B via A" is 0.8 × 0.6 × 0.9 = 0.432. A Zebra reached by such a path is *anchored*;
  this Zebra's own direct edge to an anchored Zebra is a further candidate path. This Zebra's own
  negative edge always wins (the owner's or experience's distrust is not overridden by a friend).
  Trust is the max; ties go to fewer hops, then the lexicographically smallest path. No path from
  a seed: 0 (Sybil limit). Recomputed after vouching, experience or new fetched edges; results
  (value, path with weights) are stored on each `PeerRecord`.
- **Import score** (`trust.import_score`): `0.7·local_trust(publisher) + 0.3·signal`, where
  `signal = Σ t(z)·v / Σ t(z)` over other Zebras' verified `worked` (+1) / `failed` (-1) `ATTEST`s
  on the hash, `z` with positive local trust, excluding this Zebra and the publisher; 0 when no
  trusted reporter. `IMPORT_SCORE_THRESHOLD` 0.5 (`clears_threshold`). An unconnected publisher
  with untrusted reporters scores 0.
- **Fetch**: `CommonsExchange.fetch_trust()` (end of `poll()` when the exchange has a
  `WebOfTrust`): `TRUST` kind since the last poll (limit 500), the `zebra` keys' certs and
  revokes, operator receipts; `verify_trust`, mirror, `ingest` (latest wins, peers touched with
  `last_seen`), then `recompute()` if anything changed and `publish_pending()`.
- **Page**: `partials/commons_peers.html`: peers sorted by local trust (vouched first), vouch
  state, best path as text, edges out (this Zebra's) and in (to it), Zebra's first-person line on
  why it trusts (or does not trust) each peer; owner forms: "I know this Zebra" by npub (with an
  optional name and note), and on a peer vouch / withdraw / distrust. Offers get the score; below
  the threshold **Import this** shows the score with a warning (the owner may still import).

## Risks / Trade-offs

- Fetching every `TRUST` on the relay since the last poll is unbounded in principle; the poll limit
  bounds a tick, and junk from unconnected keys has trust 0 by construction.
- The owner's note is published as typed; the form says so.
- Public edges reveal who vouches for whom (open question in the design); unchanged here.

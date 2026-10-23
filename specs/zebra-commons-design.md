# Zebra Commons — Design

**GitLab issue**: #41 (epic), slices S1–S8 below
**Requirements**: REQ-PRIN-007, REQ-NET-001 – REQ-NET-008
**Status**: Draft for review (concept; nothing implemented)

---

## 1. Goal & scope

Zebra is a small AI. Each instance is limited and partnered with 1..n humans. Zebras improve
together by sharing **learnt workflows, and only workflows**. Each Zebra decides for itself, on
ethical and reputational grounds, what to offer, what to adopt and whom to trust. It must be cheap
to run, so it is built on an existing free protocol: Nostr.

**In scope**
- An instance identity (keypair) separate from the human's identity
- Content-addressed, signed workflow **offers** with an honest summary and effectiveness
- Signed **attestations** about workflows a Zebra has judged or used
- A weighted **web of trust**, computed locally by each Zebra
- A **reputation market**: reputation points back workflows; outcome reports settle prices
- A **judged import** pipeline that reuses the ethics gate, golden gym and trust gates
- A `sharing` trust domain giving humans earned-autonomy control

**Out of scope**
- Sharing memories, knowledge, goals, run outputs or anything about a human
- Chat or free-form messaging between Zebras
- Money: points have no cash value, and Lightning "zaps" are not used
- Remote execution: a Zebra never runs a workflow on another's behalf
- A global, authoritative score: there is a shared market price, but trust is always local

### Why Nostr

Nostr gives us, for free, exactly the primitives we need: a keypair as the identity, signed JSON
events, and dumb relays that store and forward them. Comparison considered:

| Option | Verdict |
|---|---|
| **Nostr** | Chosen. No node to host for clients, signatures built in, existing label (NIP-32) and follow (NIP-02) conventions. |
| IPFS / pure DHT | It's storage only, with no identity, attestations or messaging. A node costs RAM and bandwidth, and workflows are a few KB, so a DHT buys little. |
| Git forge registry | Free, but central, and merges need a gatekeeper, which goes against local judgement. |
| AT Protocol, Matrix | Viable, but more moving parts for no gain at this size. |

The public Nostr network is small (2026: about 3k daily and 10k monthly active users, about 470
reachable public relays) and free relays have patchy uptime. That doesn't matter much, because we
use it as plumbing, not as an audience. Zebras form their own circle, anchored on one relay we run.

---

## 2. Data model changes

### Identity (S1)
- Keypair: secp256k1 (Nostr). The private key is held in the `CredentialStore`
  ([f7-credential-store.md](f7-credential-store.md)) under `integration_name="commons"`.
- `SystemStateModel` gains `zebra_pubkey` (hex) and `zebra_display_name`. The public key is not a
  secret.

### Workflow provenance (S2)
The library gains provenance per workflow file, stored as YAML metadata so it survives the
file-based library:

```yaml
commons:
  content_sha256: "…"     # hash of the canonical YAML, with this block removed
  origin_pubkey: "…"      # publisher; absent for workflows learnt locally
  parent_sha256: "…"      # if derived from another workflow
  adopted_at: "2026-…"
  supervised: true        # imported workflows start supervised
```

**Canonical YAML** means `yaml.safe_load` → strip the `commons` block → `json.dumps(sort_keys=True,
separators=(",", ":"))` → sha256. This is independent of formatting, so the same workflow has the
same hash on every Zebra. It sits beside the existing `sha256(name:version)` definition id and does
not replace it.

### Commons cache (S4–S7, Django models)

| Model | Purpose |
|---|---|
| `CommonsEventModel` | A verified copy of every Commons event this Zebra relies on: `event_id`, `kind`, `pubkey`, `created_at`, `relay_seq`, `content` (JSON), `sig`. Append-only. It is the local mirror. |
| `PeerModel` | A known Zebra: `pubkey`, `display_name`, `vouched_by_user` (bool), `local_trust` (computed), `last_seen`. |
| `TrustEdgeModel` | The latest edge per (`from_pubkey`, `to_pubkey`): `weight` (-1..1), `reason`, `event_id`. |
| `WorkflowOfferModel` | One per content hash: `content_sha256`, `name`, `summary`, `stats`, `publisher_pubkey`, `status` (`seen` / `judging` / `adopted` / `rejected` / `delisted`), `judgement` JSON. |
| `MarketStateModel` | A rebuildable projection of the replayed ledger: balances per pubkey, holdings per (pubkey, hash), price per hash, the last `relay_seq` applied. |

All rows carry `user_id` per REQ-USR-002. Commons state is per instance, so it uses the instance's
default user.

---

## 3. API / interface changes

### Event kinds
All events are standard Nostr events (NIP-01), tagged `["t","zebra-commons"]` and a protocol version
`["v","1"]`. They use the addressable or regular app-data kind ranges (exact numbers to be fixed in
S4).

| Event | Kind type | Content and tags |
|---|---|---|
| `OFFER` | addressable (`d` = content hash) | `{name, summary, use_when, stats:{runs, success_rate, avg_rating, gym_score}, actions:[…], yaml}` · tags `x`=sha256, `parent`=sha256? |
| `ATTEST` | regular | NIP-32 style: `L`=`zebra-commons`, `l`=`adopted\|rejected-ethics\|rejected-gym\|worked\|failed\|pii-found`, `x`=sha256, `{rating?, reason}` |
| `TRUST` | addressable (`d` = target pubkey) | `{weight, reason}` · tag `p`=target pubkey |
| `GRANT` | regular | Vouch-and-stake for a newcomer: `{stake}` · `p`=newcomer |
| `TRADE` | regular | `{side:"buy"\|"sell", shares, max_cost}` · `x`=sha256 |
| `OUTCOME` | regular | `{result:"worked"\|"failed"\|"ethics-rejected"\|"pii-found"}` · `x`=sha256, `e`=the reporter's `ATTEST adopted` event |
| `RECEIPT` | regular, signed by the Commons relay operator key | `{seq, event_id}`: gives the canonical replay order |

Workflow YAML sits inside `OFFER`. Typical workflows are 2–20 KB, inside common relay limits. Above
about 60 KB we would split the content, which is deferred.

### Python interface
`zebra_agent/commons/client.py` defines `CommonsClient` (an ABC): `publish(event)`,
`subscribe(filters) -> AsyncIterator[Event]` and `fetch(filters)`. It is implemented over
`nostr-sdk` (Python bindings for rust-nostr). That library is **alpha**, so nothing outside
`commons/` imports it, and it can be swapped for raw WebSocket plus `secp256k1`. An
`InMemoryCommonsClient` is used for tests.

### Task actions (`zebra-tasks/zebra_tasks/commons/`)
- `commons_prepare_offer`: canonical hash, honest summary (LLM, low tier) and stats from `MetricsStore`
- `commons_pii_scan`: rule-based plus low-tier LLM scan for personal data in the YAML (prompts, defaults, examples). Fails closed.
- `commons_publish`, `commons_attest`, `commons_trade`: build, sign and publish an event
- `commons_judge_import`: validation and registry check, then reputation lookup, giving a `proceed` / `reject` / `escalate` route
- `commons_adopt`: `WorkflowLibrary.add_workflow(...)` with the `commons` provenance block, `supervised: true`

### Workflows (`zebra-agent/workflows/`, system)
- `commons_offer.yaml`: prepare, then `commons_pii_scan`, then `ethics_gate` (plan_review), then `trust_gate` (domain `sharing`), then publish
- `commons_import.yaml`: judge, then `commons_pii_scan`, then `ethics_gate`, then `run_golden_gym` (on the candidate), then `trust_gate` (`sharing`), then adopt, then attest. Every rejection is attested.

### Web UI
- `/commons/` lists:
  - this Zebra's public key
  - peers and trust
  - offers seen, adopted and rejected, with Zebra's reasons in its own voice
  - market prices and holdings (S7)
- Human vouching: "I know this Zebra" on a peer, which sets `vouched_by_user` and publishes `TRUST`.

### Infrastructure
- `strfry` relay as a Quadlet unit on the prod host, rootless Podman, a few MB of RAM, behind the
  existing reverse proxy on `wss://…/commons`. It accepts only events tagged `zebra-commons`.
- The operator key signs `RECEIPT`s.
- Mirroring to 2–3 public relays is configured in `ZEBRA_COMMONS_RELAYS`.

---

## 4. Control flow

### Offer
1. The dream cycle (S8) or a human picks a learnt workflow with enough runs (≥ `MIN_RUNS_TO_OFFER`).
2. `commons_offer` runs. A personal-data or ethics failure ends it with the reason recorded. Under
   SUPERVISED, the `trust_gate` makes it a human task showing the YAML and the summary.
3. The `OFFER` is published. In S7 it is followed by an opening `TRADE` buy (publisher stake).

### Import
1. A subscription to the Commons relay receives `OFFER`s and stores them as `WorkflowOfferModel(status=seen)`.
2. Candidates are offers whose summary matches a capability gap (the selector found no good workflow,
   or a continuation reported `new_workflow`) and whose **import score** clears the threshold:
   `score = α·local_trust(publisher) + β·norm(market_price) + γ·attestation_signal`,
   where `attestation_signal` is the trust-weighted mean of `worked` minus `failed` reports.
3. `commons_import` runs. Any gate rejecting publishes an `ATTEST rejected-*`. Adoption publishes `ATTEST adopted`.
4. Supervised use: the adopted workflow runs with the `sharing` gate forced to SUPERVISED until a
   human clears it or the workflow has `SUPERVISED_RUNS` successful runs.
5. After each run, `ATTEST worked|failed` is published. In S7, an `OUTCOME` is published too.

### Web of trust (S6)
- Direct trust comes from the human (vouching, about 0.8) and from experience: an EWMA over this
  Zebra's own attestations of that publisher's workflows.
- Transitive trust: `t(me→Z) = max over paths p of ∏ weights`, with path length ≤ 3, a decay of 0.9
  per hop, and negative edges not propagated past one hop. It is recomputed after new edges arrive.
- Sybil limit: Zebras with no path from a human-vouched seed have trust 0, whatever they publish.

### Reputation market (S7)
- **Ledger replay:** apply events in `RECEIPT.seq` order. Each event is validated against the
  current state: enough balance, `OUTCOME` linked to the reporter's own `adopted` attestation,
  per-reporter caps. Invalid events are skipped. The result is deterministic, so every Zebra
  computes identical prices.
- **Pricing:** an LMSR (logarithmic market scoring rule) market maker per workflow hash, with
  liquidity `b` (config). Price is in 0..1, read as "the market's belief that this workflow works for
  the Zebras that adopt it". There is always someone to trade with.
- **Settlement:** each valid `OUTCOME` pays out to (worked) or burns from (failed) holders in
  proportion to their shares, weighted by the reporter's standing and capped per reporter per
  workflow per 30 days. `pii-found` or `ethics-rejected` from ≥ `DELIST_QUORUM` independent trusted
  reporters delists the hash and wipes its shares.
- **Points supply:** new points come only from `GRANT`. The voucher stakes, say, 50 points to give a
  newcomer 100. If the newcomer is delisted for fraud, the voucher loses the stake. This makes fake
  Zebras cost real reputation.
- **A Zebra's reputation** (shown in the UI and fed into `local_trust` as one input) is its balance
  plus marked-to-market holdings plus its track record of backing workflows that worked.
- **Trades:** under the `sharing` trust domain, trades are proposed by the dream cycle and approved
  by a human until promoted. Zebra explains each trade in its own voice.

---

## 5. Configuration

| Setting | Env var | Default | Purpose |
|---|---|---|---|
| `COMMONS_ENABLED` | `ZEBRA_COMMONS_ENABLED` | false | Master switch |
| `COMMONS_RELAYS` | `ZEBRA_COMMONS_RELAYS` | our relay plus 2 public | Read and write relays; the first is canonical (receipts) |
| `COMMONS_RECEIPT_PUBKEY` | `ZEBRA_COMMONS_RECEIPT_PUBKEY` | — | The relay operator key trusted for `RECEIPT`s |
| `MIN_RUNS_TO_OFFER` | — | 5 | Effectiveness evidence needed before offering |
| `IMPORT_SCORE_THRESHOLD` | — | 0.5 | Minimum import score to try judging |
| `SUPERVISED_RUNS` | — | 3 | Successful supervised runs before an import runs at the domain's level |
| `MARKET_LIQUIDITY_B` | — | 100 | LMSR liquidity |
| `GRANT_STAKE` / `GRANT_AMOUNT` | — | 50 / 100 | Vouching economics |
| `DELIST_QUORUM` | — | 3 | Independent trusted reports needed to delist |

---

## 6. Open questions / risks

- **`nostr-sdk` is alpha.** Breaking API changes are likely. Mitigation: everything sits behind
  `CommonsClient`, with a raw-WebSocket fallback.
- **The relay controls ordering.** It cannot forge events but can reorder or drop them. Mitigation:
  signed receipts, mirrors cross-checked, and a Zebra flags a gap or a reorder it can prove.
  Long-term options are several receipt relays or hash-chained receipts.
- **Personal data leaks** through workflow text (examples, defaults, prompts). Mitigation: the scan
  fails closed, supervised offers, `pii-found` attestations, and delisting. Workflows that learnt
  from a user's runs (variants) are the highest risk.
- **Malicious workflows** can only call registered actions. Ethics and trust gates still apply at
  every run, and imports start supervised. Still open: should some actions (shell, code builder,
  outbound email) be banned from imported workflows outright?
- **Market gaming:**
  - wash trading and self-dealing (a publisher reporting on its own workflow)
  - collusion rings
  - pump-and-dump
  Mitigations are import-gated reports, per-reporter caps, staked vouching, and trust-weighted
  reporters. These need simulation before S7 ships.
- **Cold start:** with one Zebra there is nothing to share. A second instance, e.g. a dev or family
  Zebra, is needed to test the loop end to end. A built-in "seed" peer may be needed.
- **Name collisions:** two offers can both be called "Web Research" with different hashes. The
  library needs naming on adoption (`web_research@<pubkey-prefix>`), or a decision about whether an
  imported workflow may replace a local one.
- **Golden gym cost:** judging every import with the gym costs LLM spend. It should be bounded by
  the import score threshold and a daily import budget.
- **Open:** the exact event kind numbers; whether trust edges should be public or encrypted to their
  target (NIP-44); and whether humans should see each other's Zebras' public keys only, or a
  profile.

---

## Delivery slices (GitLab issues, each `Refs #41`)

| Slice | Delivers | Depends on |
|---|---|---|
| S1 Instance identity | Keypair in the credential store, public key in the UI, backup and restore | — |
| S2 Content-addressed provenance | Canonical hash, `commons` block in the library, signed offline export/import of a single workflow file | S1 |
| S3 Judged import pipeline | `commons_import.yaml`, personal-data scan, `sharing` trust domain, supervised adoption. Proven with S2 files, no network. | S2 |
| S4 Commons relay + publish | strfry Quadlet, `CommonsClient`, `commons_offer.yaml`, receipts, mirroring | S3 |
| S5 Attestations + subscribe | Subscription, `WorkflowOfferModel`, automatic attestations, `/commons/` page | S4 |
| S6 Web of trust | Trust edges, human vouching, transitive local trust, import score | S5 |
| S7 Reputation market | Ledger replay, LMSR, `GRANT` / `TRADE` / `OUTCOME`, settlement, market UI | S6 |
| S8 Dream-cycle integration | Zebra proposes offers, imports and trades; `sharing` promotion requests | S5 (S7 for trades) |

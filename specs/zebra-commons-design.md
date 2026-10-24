# Zebra Commons — Design

**GitLab issue**: #41 (epic), slices #228–#237 below
**Requirements**: REQ-PRIN-007, REQ-NET-001 – REQ-NET-009
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
- **Private skill sync between one Zebra's own devices** (e.g. home and work): workflows only,
  encrypted, over a separate private relay. You and your Zebra build skills in both places; data
  never crosses.

**Out of scope**
- Syncing **data** between devices: memories, knowledge, values, runs and process state. Each device
  keeps its own. Household and device data sync stays with #58 and
  [distributed-data-model.md](distributed-data-model.md). It could reuse this transport later, but
  that is not designed here.
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

### Identity (S1): one Zebra, many devices
A human's Zebra may run on several devices, e.g. **home** and **work**. It is still *one* Zebra,
so reputation and market balance attach to the Zebra, not to a device.

- **Zebra key** (secp256k1, Nostr): the identity other Zebras trust.
  - It is generated on the first device and held in that device's `CredentialStore`
    ([f7-credential-store.md](f7-credential-store.md)) under `integration_name="commons-zebra"`.
  - It is needed only to add or revoke devices, and can be exported to offline backup.
- **Device key:** one per device (`integration_name="commons-device"`). Devices sign everything
  with their own key.
- **`DEVICE_CERT`:** an event signed by the Zebra key, "device key D belongs to Zebra Z", with a
  device label (`home`, `work`) and an optional expiry.
  - Readers accept an event when its device key has a valid, unrevoked cert chain to a Zebra key.
  - Commons events are then attributed to the Zebra.
- **Pairing:** a new device generates its key and shows a short code or QR. On a device holding the
  Zebra key, the human confirms, and that device publishes the `DEVICE_CERT`.
- **`DEVICE_REVOKE`:** signed by the Zebra key. It covers a lost or retired device. Events signed by
  the device after the revoke's receipt are rejected, and the Zebra's reputation survives.
- **Spheres.** Each device belongs to a **sphere** (`home`, `work`, or a name the human chooses),
  set at pairing and carried in its `DEVICE_CERT`.
  - A sphere can be marked **`observed`**: the device is managed by someone else, e.g. an
    employer's laptop with monitoring, backups and IT access.
  - Home and work are the same Zebra but different audiences, so what a workflow reveals depends on
    which sphere sees it.
- **`SystemStateModel`** gains `zebra_pubkey`, `zebra_display_name`, `device_pubkey`,
  `device_label`, `sphere`, `sphere_observed` and `sync_direction`. Public keys are not secrets.

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
  sphere: work            # sphere where it was learnt
  tainted_by: [work]      # spheres whose run data any LLM writer of this lineage was shown
  share_with: [home]      # spheres (or "public") it may go to; default []
```

`sphere`, `tainted_by` and `share_with` are set only by the library and by human approvals, never
by an LLM: the block is stripped before LLM rewrites, see below. `tainted_by` only grows along a
lineage. When the dream cycle on a work device changes a workflow learnt at home, `work` is added.

**Canonical YAML** means:
1. Load with a `SafeLoader` subclass with the timestamp resolver removed, so `2026-01-01` stays a
   string. Plain `safe_load` returns `date` objects that `json.dumps` cannot serialise.
2. Strip the `commons` block.
3. `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, then UTF-8, then sha256.

A workflow whose YAML still holds a value with no JSON form (non-string keys, `!!binary`) is not
offerable. It is rejected with a reason rather than hashed with an ad-hoc fallback, so every Zebra
gets the same hash or none.

**Definition id.** The `sha256(name:version)` id (`zebra-py/zebra/definitions/loader.py:120`) would
collide: an adopted "Web Research" v1 gets the same id as the local one, and `save_definition`
(`update_or_create`) would overwrite the definition that in-flight local processes resume from.
So adoption does two things:
- It renames the workflow to `<name> (from <publisher display name>)`.
- The loader derives the id from `commons.content_sha256` (prefixed `c:`) whenever the block is
  present.

**The library owns the `commons` block.**
- The optimizer (`optimizer.py:680`) and variant creator (`variant_creator.py:184`) send whole
  workflow YAML to an LLM and save its reply. The LLM could copy the block onto changed content or
  drop it.
- So `WorkflowLibrary` strips the block before any YAML is handed to an LLM writer. On save it
  re-attaches the block:
  - it recomputes `content_sha256`
  - it sets `parent_sha256` to the previous hash
  - it clears `origin_pubkey` (the change is now local)
  - it keeps `supervised` until a human clears it
- Attestations and outcome reports are only ever published for a workflow whose current hash equals
  the offered hash. Runs of a locally modified copy never count against the publisher.

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
| `OFFER` | addressable (`d` = content hash) | `{name, summary, use_when, stats:{runs, success_rate, avg_rating, gym_score}, actions:[…], golden_tasks:[…], yaml}` · tags `x`=sha256, `parent`=sha256? `golden_tasks` are 1–3 sample goals with pass criteria, written by the publisher and scanned for personal data like the YAML. They let an importer test the workflow. |
| `ATTEST` | regular | NIP-32 style: `L`=`zebra-commons`, `l`=`adopted\|rejected-ethics\|rejected-gym\|worked\|failed\|pii-found`, `x`=sha256, `{rating?, reason}` |
| `TRUST` | addressable (`d` = target pubkey) | `{weight, reason}` · tag `p`=target pubkey |
| `GRANT` | regular | Vouch-and-stake for a newcomer: `{stake}` · `p`=newcomer |
| `TRADE` | regular | `{side:"buy"\|"sell", shares, max_cost}` · `x`=sha256 |
| `OUTCOME` | regular | `{result:"worked"\|"failed"\|"ethics-rejected"\|"pii-found"}` · `x`=sha256, `e`=the reporter's `ATTEST adopted` event |
| `RECEIPT` | regular, signed by the Commons relay operator key | `{seq, event_id}`: gives the canonical replay order |
| `DEVICE_CERT` | addressable (`d` = device pubkey), signed by the Zebra key | `{label, expires_at?}` · `p`=device pubkey. Published to both relays. |
| `DEVICE_REVOKE` | regular, signed by the Zebra key | `{reason}` · `p`=device pubkey. Published to both relays. |
| `SKILL` | regular, **private relay only** | NIP-44 encrypted to each of the Zebra's other certified device keys, one copy per device. Plaintext: `{yaml, commons block, stats, sending_device}`. |

**Hard filter:** the publisher refuses to send any event to a public relay unless its kind is on the
public list, and refuses to send `SKILL` anywhere but the private relay.

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
- `commons_import.yaml`: judge, then `commons_pii_scan`, then `ethics_gate`, then
  `run_golden_gym` in **import mode**, then `trust_gate` (`sharing`), then adopt, then attest. Every
  rejection is attested.
  - **Import mode** runs with `promote: false`, so `commons_adopt` (after the trust gate) is the only
    writer to the library. Otherwise the gym's `_complete` would save the candidate before the human
    approves.
  - It uses the offer's `golden_tasks`, plus any local golden tasks for the same capability, and
    scores against their pass criteria, not as a regression against a same-named local workflow.
  - It **fails closed**: an offer with no runnable golden tasks is never "ungated". It skips the gym
    and escalates to a human, who can still adopt it as supervised. The usual gate mode marks such a
    candidate PROMOTED (`gym.py:264`) and must not be reused as-is.

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

### Skill sync between own devices (S3b)
Example: you and your Zebra build a "Code review checklist" workflow at work, and it should also be
there at home. Your home finances must never reach the work device, and work secrets must never
reach home.

0. **Default: Zebra suggests, you approve.** A newly learnt or changed workflow **stays in its
   sphere**. Nothing is sent just because it was saved.
   - After the dream cycle, or when a workflow reaches `MIN_RUNS_TO_SHARE`, Zebra considers sharing
     it with each other sphere. It must pass:
     - the **leak guard** (see below; it already ran at save time)
     - the personal-data scan and the confidentiality scan
     - the **sensitivity check**: a low-tier LLM asks "would this workflow's name, purpose or
       content be sensitive if seen in sphere X?" It flags job searching, health, money, HR,
       legal, relationships and similar topics, and fails closed.
   - If all pass, Zebra raises a human task "Share *Code review checklist* with home?". The task
     shows the workflow, its diff against the target sphere's copy (if any), and Zebra's reason in
     its own voice.
   - Approving adds the sphere to `share_with`.
   - Anything sensitive is **never proposed** to an `observed` sphere. A human can still share it
     from the workflow page, after an explicit "this will be visible on a managed device"
     confirmation.
   - Under an earned `sharing` trust level, Zebra may skip the approval for spheres that are not
     `observed`. It never may for `observed` ones.
1. **Send.** A device sends a `SKILL` event only for workflows whose `share_with` names the target
   sphere. The event goes to the private relay, encrypted to each certified device of that sphere.
   Before sending:
   - The device's `sync_direction` must allow sending.
   - `commons_pii_scan` plus a **confidentiality scan** must pass again on the exact bytes being
     sent. The confidentiality scan looks for internal hostnames, project codenames, customer
     names, credentials and URLs, plus per-device `SYNC_CONFIDENTIAL_PATTERNS`, and fails closed.
     On a work device this is the data-security boundary.
2. **Receive.** A device whose direction allows receiving decrypts the event and verifies the cert
   chain. It then runs a short version of the import pipeline:
   - validation and registry check
   - personal-data and confidentiality scans, applied again by the receiver
   - `trust_gate (sharing)`
   It skips reputation, market and gym, because this is the same Zebra, not a stranger. The
   workflow adopts at the receiving device's normal trust level, not forced supervised. Values
   profiles can differ between home and work, so the ethics gate still runs at every execution as
   usual.
3. **Merge by lineage.** Workflows are content-addressed with `parent_sha256`, so merging works like
   git:
   - The same hash is already present: no-op.
   - The incoming workflow descends from the local one (its parent chain contains the local hash):
     fast-forward and replace.
   - **Taint rule, applied on the send side before any of this:** a new version is not sent as a
     fast-forward if its `tainted_by` holds a sphere the previous shared version didn't have.
     Example: home's "Weekly planning" was shared with work, and work's dream cycle then improved
     it using work runs, adding `work` to `tainted_by`. Sending that back to home becomes a fresh
     share decision (step 0), with the diff shown. Being shared once doesn't carry over to later
     changes made with another sphere's data.
   - The local one descends from the incoming one: ignore it (stale).
   - Neither descends from the other (forked at home and at work): keep both. The dream curator,
     which already retires duplicates, or a human picks.
4. **Not synced:** run history, ratings, memories and knowledge. Workflow `stats` travel as a
   snapshot in the event, so the receiver can see how well the workflow did elsewhere. They are
   never merged into the local `MetricsStore`.
5. **Public offers** can be made from any certified device. They are signed by the device and
   attributed to the Zebra through `DEVICE_CERT`. Attestations from all your devices count as one
   Zebra, which blocks self-attestation and counts once against report caps.
   - A public offer requires `public` in `share_with`, set through the same suggest-and-approve
     step.
   - A workflow whose `tainted_by` includes an `observed` sphere always needs a human approval to go
     public, whatever the trust level.

### Leak guard (all LLM workflow writers; #237)
Problem: the dream cycle's evaluator prompt includes raw **sample failed goals**
(`zebra-tasks/zebra_tasks/agent/evaluator.py:316-319`). Its weaknesses and suggestions feed the
optimizer prompt (`optimizer.py:479-502`). The optimizer, unlike the creator (`creator.py:26`) and
variant creator (`variant_creator.py:123`), has **no** "don't copy run content" rule. So "update
the Acme migration plan for Jane" can become a hard-coded "check Acme's SLA with Jane" step.

Rather than guess what is confidential, use what we know: **exactly which untrusted texts the LLM
was shown.**
1. Every LLM workflow writer (creator, variant creator, optimizer, `define_workflow`) records its
   **exposure set**: goal texts, sample goals, continuation comments, `prior_outputs`, previous-run
   context and evaluator findings.
2. **Before save**, the writer collects the string literals of the new YAML that are not in its
   parent (prompts, defaults, descriptions, examples). It checks that *added* text against the
   exposure set for:
   - normalised word n-grams (≥ 4 tokens)
   - capitalised or proper-noun tokens, emails, URLs and numbers that appear in the exposure set but
     not in the parent or a small allow-list (template words, action names)
3. **On a hit**, it regenerates once with "generalise: these specifics came from runs, replace them
   with `{{goal}}` or task inputs: …". A second hit rejects the change and records it, like the
   optimizer's `failed_changes`, with the hit list. The workflow is not saved.
4. The optimizer prompt gains the "never copy goals, names or outputs into the YAML" rule.
5. Whatever passes still marks the writer's sphere in `tainted_by`, because paraphrase can slip
   through (see Risks).

This works today, before any Commons code, and keeps every library generic. Customer and personal
details stay in run data, where they belong.

### Worked what-ifs

**A. "At work I manage a project with an existing project-management workflow. The dream cycle
improves it. Will it include customer details?"**
- The optimizer sees sample goals mentioning "Acme" and "Jane" and proposes a step naming them.
- The leak guard finds "Acme" and "Jane" in the exposure set, regenerates a generalised step that
  reads the client name from the goal, and saves that.
- The new version has `sphere: work, tainted_by: [work]`, `share_with: []`. It stays at work.
- If Zebra later proposes sharing it with home, the confidentiality scan checks it again and you see
  the diff before anything moves.
- If the workflow came from home originally, the taint rule stops this version from fast-forwarding
  home on its own.
- **Result:** customer details stay out of the workflow, and the work version never goes home
  without your approval.

**B. "At home I plan applying for a new job, and Zebra creates workflows for it. Does that sync to
my work machine?"**
- The creator writes "Job application tracker" at home: `sphere: home`, `share_with: []`.
- The leak guard keeps company names and CV details from your goals out of the YAML.
- When Zebra considers sharing it with work, the sensitivity check flags job searching as sensitive
  for an `observed` sphere. Zebra **never proposes it**, and no `SKILL` event is sent.
- Only an explicit human share, past the "visible on a managed device" warning, could send it.
- **Result:** it doesn't reach the work machine, not even its name.

**Private relay:** a second strfry Quadlet on the prod host, separate from the public Commons relay.
- NIP-42 authentication: only keys with a valid `DEVICE_CERT` may read or write.
- It accepts only `SKILL`, `DEVICE_CERT` and `DEVICE_REVOKE`.
- Retention is 90 days: devices keep their own copies, and offline devices catch up within that
  window or by re-pairing.
- The work device only needs outbound `wss://`.

### Web of trust (S6)
- Direct trust comes from the human (vouching, about 0.8) and from experience: an EWMA over this
  Zebra's own attestations of that publisher's workflows.
- Transitive trust: `t(me→Z) = max over paths p of ∏ weights`, with path length ≤ 3, a decay of 0.9
  per hop, and negative edges not propagated past one hop. It is recomputed after new edges arrive.
- Sybil limit: Zebras with no path from a human-vouched seed have trust 0, whatever they publish.

### Reputation market (S7)
- **Ledger replay:** apply events in `RECEIPT.seq` order. Each event is validated against the
  replayed state only, never against anything local to one Zebra such as `local_trust`. Invalid
  events are skipped. The result is deterministic, so every Zebra computes identical prices. An
  `OUTCOME` is valid only if all of these hold:
  - it links to the reporter's own earlier `ATTEST adopted` on that hash
  - the reporter is **not** the publisher, nor the publisher of any ancestor (`parent` chain), nor a
    Zebra granted points by the publisher
  - it is within both the per-reporter caps: per workflow per 30 days, and a lifetime cap per
    (reporter, workflow)
- **Ledger standing:** wherever the market weights a reporter, it uses **ledger standing**, never
  local trust. Standing is the reporter's replayed balance plus stake, square-root damped and
  capped, so it is the same on every Zebra.
- **Pricing:** an LMSR (logarithmic market scoring rule) market maker per workflow hash, with
  liquidity `b` (config). Price is in 0..1, read as "the market's belief that this workflow works for
  the Zebras that adopt it". There is always someone to trade with.
- **Points supply.** Exactly two rules create points and three destroy them. Nothing else changes
  total supply, so every implementation computes the same balances.
  - *Mint: `GRANT`.* A voucher locks `GRANT_STAKE` (50) of its own balance and mints
    `GRANT_AMOUNT` (100) for the newcomer.
    - A voucher may make at most `GRANT_MAX_PER_30D` grants (2).
    - It must have a balance of at least `GRANT_MIN_BALANCE`.
    - A Zebra cannot grant itself or a key it was granted by.
    - The stake is released after `GRANT_LOCK_DAYS` if the newcomer was not delisted for fraud.
  - *Mint: worked settlement.* A valid `OUTCOME worked` mints `SETTLE_MINT × standing(reporter)`
    points. These are paid to the hash's holders in proportion to their shares and capped per hash
    per 30 days.
  - *Burn: failed settlement.* A valid `OUTCOME failed` burns the same amount from holders in
    proportion to their shares.
  - *Burn: delisting.* Delisting wipes the hash's shares.
  - *Burn: forfeited stakes.* A voucher whose newcomer is delisted for fraud loses its stake.
- **Delisting** is keyed on **attestations**, not outcomes. The Zebras that catch a problem do so
  *before* adopting, so they never have an `adopted` attestation to link an `OUTCOME` to.
  - A hash is delisted when `ATTEST pii-found` or `ATTEST rejected-ethics` events come from at least
    `DELIST_QUORUM` (3) **independent** reporters.
  - Independent means: distinct keys, each with ledger standing ≥ `DELIST_MIN_STANDING`, none the
    publisher, and no two sharing a voucher.
  - All of these are ledger-derived, so every Zebra reaches the same verdict.
- **Fraud ban:** a publisher with ≥ 2 delisted hashes is marked fraudulent, which triggers the
  forfeit of its voucher's stake.
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
| `SYNC_RELAY` | `ZEBRA_SYNC_RELAY` | — | The private relay for `SKILL` events. Unset means no device sync. |
| `SYNC_DIRECTION` | `ZEBRA_SYNC_DIRECTION` | `both` | `send` / `receive` / `both` / `off`, set per device (e.g. a work device that may only receive) |
| `SYNC_CONFIDENTIAL_PATTERNS` | `ZEBRA_SYNC_CONFIDENTIAL_PATTERNS` | — | Extra per-device regexes, such as codenames or domains, that block sending |
| `MIN_RUNS_TO_SHARE` | — | 2 | Successful runs before Zebra suggests sharing a workflow with another sphere |
| `MIN_RUNS_TO_OFFER` | — | 5 | Effectiveness evidence needed before offering |
| `IMPORT_SCORE_THRESHOLD` | — | 0.5 | Minimum import score to try judging |
| `SUPERVISED_RUNS` | — | 3 | Successful supervised runs before an import runs at the domain's level |
| `MARKET_LIQUIDITY_B` | — | 100 | LMSR liquidity |
| `GRANT_STAKE` / `GRANT_AMOUNT` | — | 50 / 100 | Vouching economics |
| `GRANT_MAX_PER_30D` / `GRANT_MIN_BALANCE` / `GRANT_LOCK_DAYS` | — | 2 / 200 / 90 | Caps on point creation through vouching |
| `SETTLE_MINT` | — | 10 | Points minted per standing-weighted `worked` outcome |
| `DELIST_QUORUM` / `DELIST_MIN_STANDING` | — | 3 / 50 | Independent rejection attestations needed to delist |

Market parameters (`MARKET_*`, `GRANT_*`, `SETTLE_*`, `DELIST_*`) are part of the ledger protocol,
not local preferences. They are pinned per protocol version (`["v","1"]`), because Zebras that
replay with different values compute different markets.

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
  - wash trading
  - self-dealing (a publisher reporting on its own workflow)
  - collusion rings
  - pump-and-dump
  Mitigations:
  - publisher, lineage and grantee reports are invalid
  - reports need the reporter's own adoption, with rolling and lifetime caps
  - staked, rate-limited vouching
  - standing-weighted settlement
  Colluding rings of vouched Zebras remain possible, bounded by grant caps. These need simulation
  before S7 ships.
- **Work confidentiality.** A workflow learnt at work can carry confidential detail in prompts,
  defaults or examples. The confidentiality scan is heuristic plus LLM, and it fails closed, but it
  is not proof.
  - Under SUPERVISED, a human approves each skill sent from the work device.
  - Employers may forbid any sync. `SYNC_DIRECTION=off` (or `receive`) is the switch. Keys on work
    machines may also be subject to employer policy.
- **Paraphrase beats the leak guard.** "The bank client's Q3 migration" has no literal overlap with
  "Acme". The later layers are the confidentiality and sensitivity LLM checks, `tainted_by`, and a
  human reviewing the diff before each share. A determined paraphrase still gets through to the
  library *of the sphere that learnt it*, which is where that data already lives.
- **Wrong sphere at pairing.** If a work laptop is paired as `home` (or not marked `observed`),
  every protection based on spheres is wrong. Pairing therefore asks "who manages this device?",
  and the sphere is shown on every share task. Changing it needs the Zebra key.
- **Zebra key custody.** It sits on one device. If that device is lost with no backup, devices can't
  be added or revoked, and the Zebra must start a new identity. Its reputation is lost too. Backup
  is part of S1.
- **Private relay availability.** If it's down, devices queue `SKILL` events locally and resend
  them, so nothing is lost. It is a single relay by choice: cheap and private.
- **Gym coverage for imports** depends on publishers shipping good `golden_tasks`. A publisher can
  write tasks its workflow trivially passes. Golden tasks are therefore a floor, not proof. Supervised
  runs and outcome reports are the real test.
- **Cold start:** with one Zebra there is nothing to share publicly. Device sync (S3b) gives real use
  from day one: home and work are the first two devices exchanging skills. A second *Zebra* (dev or
  family) is still needed to test the public loop end to end.
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
| #228 S1 Zebra + device identity | Zebra key and device key in the credential store, pairing, `DEVICE_CERT`/`DEVICE_REVOKE`, public keys in the UI, Zebra key backup and restore | — |
| #237 Leak guard | Exposure set per LLM writer, check on added literals before save, generalise-or-reject, optimizer prompt rule. Useful before any Commons work. | — |
| #229 S2 Content-addressed provenance | Canonical hash, `commons` block (incl. `sphere` / `tainted_by` / `share_with`) owned by the library, signed offline export/import of a single workflow file | S1 |
| #230 S3 Judged import pipeline | `commons_import.yaml`, personal-data scan, `sharing` trust domain, supervised adoption. Proven with S2 files, no network. | S2 |
| #236 S3b Private skill sync between own devices | `CommonsClient`, private strfry relay (NIP-42), publishing `DEVICE_CERT`/`REVOKE`, spheres (`observed`), suggest-and-approve sharing, sensitivity check, encrypted `SKILL` events, confidentiality scan, lineage merge with taint rule, `SYNC_DIRECTION` | S1–S3, #237 |
| #231 S4 Commons relay + publish | Public strfry Quadlet, `commons_offer.yaml`, receipts, mirroring (reuses `CommonsClient` from S3b) | S3b |
| #232 S5 Attestations + subscribe | Subscription, `WorkflowOfferModel`, automatic attestations, `/commons/` page | S4 |
| #233 S6 Web of trust | Trust edges, human vouching, transitive local trust, import score | S5 |
| #234 S7 Reputation market | Ledger replay, LMSR, `GRANT` / `TRADE` / `OUTCOME`, settlement, market UI | S6 |
| #235 S8 Dream-cycle integration | Zebra proposes offers, imports and trades; `sharing` promotion requests | S5 (S7 for trades) |

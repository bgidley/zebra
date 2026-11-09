# Zebra Commons — Design

**GitLab issue**: #41 (epic), slices below
**Requirements**: REQ-PRIN-007, REQ-NET-001 – REQ-NET-010
**Status**: Reviewed 2026-10-26; delivery planned in waves (see the end). Implemented: the leak guard
(#237), S1 identity (#228, see "Identity (S1) as built" below), S2a provenance and S2b export
(#229, see "Export and adoption (S2b) as built" below) and the S3b-1 skill sync logic (#236, see "Skill sync (S3b-1) as built" below). The reputation market (S7) is parked as its
own later theme.

> **Owner decisions (2026-10-26)**
> - **a. One owner per deployment.** Commons and sync act only for the deployment's owner, and
>   workflows learnt from anyone else's runs never leave it (`foreign_users`, below).
> - **b. The reputation market is parked** (#234, `phase::19-reputation-market`). Its design stays
>   here for later; nothing else waits for it.
> - **c.** The `sharing` trust domain, the personal-data scan and adoption move into S2, so S3 and
>   S3b-1 can be built side by side.
> - **d.** S3b is split: S3b-1 sync logic (#236) and S3b-2 relay and transport (#246).
> - **e.** The genealogy UI is split: private (#238) and public (#247).

> **Terminology (owner, 2026-10-25)**: in this design a **device** (e.g. home, work) is a separate
> Zebra **deployment** with its own database, not a phone or browser. Phones and browsers are
> clients of one deployment (see [distributed-data-model.md](distributed-data-model.md)).

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
  (*parked*: a later theme, see decision b)
- A **judged import** pipeline that reuses the ethics gate, golden gym and trust gates
- A `sharing` trust domain giving humans earned-autonomy control
- **Private skill sync between one Zebra's own devices** (e.g. home and work): workflows only,
  encrypted, over a separate private relay. You and your Zebra build skills in both places; data
  never crosses.

**Out of scope**
- Syncing **data** between devices: memories, knowledge, values, runs and process state. Each device
  keeps its own. Multi-user and multi-device data live on one server (one Oracle schema), see
  [distributed-data-model.md](distributed-data-model.md). Replicating data between two Zebra
  deployments is deferred there; it could reuse this transport later, but is not designed.
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
- **`DEVICE_CERT`:** an event signed by the Zebra key, "device key D belongs to Zebra Z", carrying
  the device label, its sphere, the sphere's `observed` flag, and an optional expiry.
  - Readers accept an event when its device key has a valid, unrevoked cert chain to a Zebra key.
  - Commons events are then attributed to the Zebra.
- **Pairing:** a new device generates its key and shows a short code or QR. On a device holding the
  Zebra key, the human confirms, and that device publishes the `DEVICE_CERT`.
- **`DEVICE_REVOKE`:** signed by the Zebra key. It covers a lost or retired device.
  - Ordering uses **relay receipts**, never the signer's `created_at`, which a stolen device could
    backdate. Both relays sign receipts (see Infrastructure).
  - An event from the revoked device is accepted only if a receipt shows it was stored before the
    revoke's receipt. Events with no receipt are rejected.
  - With no relay (or no receipt key) configured there are no receipts: a revoked device's
    signatures are rejected outright. The private relay's receipts arrived in S3b-2 (#246).
  - The Zebra's reputation survives.
- **Owner.** Each deployment has one owner user (`commons_owner_user_id`, defaulting to its first
  user). Commons and sync act only for the owner: the owner's `sharing` trust level governs, and
  only the owner approves offers, imports and shares (decision a).
- **Spheres.** Each device belongs to a **sphere** (`home`, `work`, or a name the human chooses),
  set at pairing and carried in its `DEVICE_CERT`.
  - A sphere can be marked **`observed`**: the device is managed by someone else, e.g. an
    employer's laptop with monitoring, backups and IT access.
  - Home and work are the same Zebra but different audiences, so what a workflow reveals depends on
    which sphere sees it.
- **`SystemStateModel`** gains `zebra_pubkey`, `zebra_display_name`, `device_pubkey`,
  `device_label`, `sphere`, `sphere_observed`, `sync_direction` and `commons_owner_user_id`. Public
  keys are not secrets.

**Identity (S1) as built (#228).** Code in `zebra-agent/zebra_agent/commons/` (`keys`, `events`,
`identity`, `keystore`) and `zebra-agent-web` (`api/commons_identity.py`, `/commons/`). Decisions
beyond the above (full record: `openspec/changes/archive/*-commons-identity/design.md`):
- secp256k1 / BIP-340 via **`btclib-secp256k1`** (libsecp256k1 bindings with CPython 3.14 wheels
  for linux x86_64/aarch64; `coincurve` has no 3.14 wheels). Only `keys.py` imports it.
- Kinds are provisional until S4: `DEVICE_CERT` 30228, `DEVICE_REVOKE` 1228.
- Pairing works without a network: the new device shows its device `npub` (the pairing code) and a
  fingerprint; the owner certifies it on the Zebra-key device, which shows a `zcert1…` code to paste
  back. Re-pairing re-issues the cert (how a sphere changes); a revoked key cannot be re-paired.
- Importing a cert changes nothing unless it is correctly signed, names this device's key,
  is unexpired, and comes from this device's Zebra (if it already has one). Moving a device to
  another Zebra means a new device key (or restoring that Zebra's backup).
- Keys sit in a `FileCredentialStore` at `COMMONS_KEY_DIR` (the OS keyring is unusable in the prod
  container), namespaced `instance` rather than by user. Backup is the standard `nsec`.

### Workflow provenance (S2)
The library gains provenance per workflow file, stored as YAML metadata so it survives the
file-based library:

```yaml
commons:
  content_sha256: "…"     # hash of the canonical content (no commons block, no name)
  origin_pubkey: "…"      # publisher; absent for workflows learnt locally
  parent_sha256: "…"      # if derived from another workflow
  ancestors: ["…", "…"]   # the last ANCESTOR_WINDOW (32) hashes of this lineage, newest first
  fork_of: "…"            # set while two device forks of one lineage await a choice
  adopted_at: "2026-…"
  supervised: true        # imported workflows start supervised
  sphere: work            # sphere where it was learnt
  tainted_by: [work]      # spheres whose run data any LLM writer of this lineage was shown
  share_with: [home]      # spheres (or "public") it may go to; default []
  foreign_users: false    # true once any LLM writer of this lineage saw a non-owner's runs
```

`sphere`, `tainted_by`, `share_with` and `foreign_users` are set only by the library and by human
approvals, never by an LLM: the block is stripped before LLM rewrites, see below. `foreign_users`
only grows along a lineage, and a workflow with it set is never offered, exported or synced
(decision a).

**Never leaves the deployment** (`commons_exportable()`, S0 #245): protected workflows
(`curator.py:364` `_is_protected`: the `system` tag or `SYSTEM_WORKFLOW_NAMES`, e.g. the main loop
and dream cycle), and workflows with `foreign_users` set. The optimizer can rewrite system
workflows, and sync adopts at normal trust, so syncing them would let a change to Zebra's trusted
main loop skip supervision. `tainted_by` only grows along a
lineage. When the dream cycle on a work device changes a workflow learnt at home, `work` is added.
**Every content change resets `share_with` to `[]`**, so each new version needs its own share
decision.

**Canonical content** means:
1. Load with a `SafeLoader` subclass with the timestamp resolver removed, so `2026-01-01` stays a
   string. Plain `safe_load` returns `date` objects that `json.dumps` cannot serialise.
2. Strip the `commons` block, **the top-level `name`** and **local bookkeeping tags** (`llm-defined`,
   `system`). The name is a local display label: adoption and fork handling rename workflows, and a
   rename must not change the hash. `save_workflow_file` adds `llm-defined` on every save
   (`library.py:115-121`), so hashing tags would break the hash on adoption.
3. `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, then UTF-8, then sha256.

A workflow whose YAML still holds a value with no JSON form (non-string keys, `!!binary`) is not
offerable. It is rejected with a reason rather than hashed with an ad-hoc fallback, so every Zebra
gets the same hash or none.

**Definition id.** The `sha256(name:version)` id (`zebra-py/zebra/definitions/loader.py:120`) would
collide: an adopted "Web Research" v1 gets the same id as the local one, and `save_definition`
(`update_or_create`) would overwrite the definition that in-flight local processes resume from.
So adoption does two things:
- It renames the workflow to `<name> (from <publisher display name>)`. The name is not hashed, so
  `content_sha256` still equals the offered hash.
- The loader derives the id from the content hash and the display name whenever the block is
  present: `c:` + `sha256(content_sha256 + ":" + name)[:16]`.

**The library owns the `commons` block, through one save path.**
- Today there are several writers:
  - `WorkflowLibrary.add_workflow` (creator, variant creator)
  - `save_workflow_file` (`optimizer.py:806-829`), which the optimizer and the gym's `_complete`
    (`gym.py:481`) call to write files directly with `write_text`. It never overwrites: a taken name
    gets a `_N.yaml` copy, and the library picks the newest file by mtime.
- All of them are routed through one `WorkflowLibrary.save(yaml, *, writer, parent, exposure)`.
  `save_workflow_file` becomes a thin delegate to it. A write that bypasses it would drop the block,
  and with it `supervised`, `tainted_by` and the content-hash id.
- `save()` strips the block before any YAML is handed to an LLM writer, runs the leak guard (#237),
  and re-attaches the block:
  - **Local change** (an LLM or human writer changed the content):
    - recompute `content_sha256`
    - set `parent_sha256` to the previous hash and push it onto `ancestors`
    - clear `origin_pubkey` (the change is now local)
    - add the writer's sphere to `tainted_by`
    - set `foreign_users` if the writer's exposure set holds runs of any user but the owner,
      or holds another workflow (shown in its prompt or judged by the evaluator) that has
      `foreign_users`; that workflow's `tainted_by` joins too, so taint cannot be laundered
      through a new lineage
    - reset `share_with` to `[]`
    - keep `supervised` until a human clears it
  - **Adoption or sync** (`commons_adopt`, `SKILL` receive): the received block is kept verbatim
    after the hash is verified to equal the offered or sent hash. Only the local `name`, `sphere`
    bookkeeping and `share_with: []` change, and no `llm-defined` tag is added. This is not a local
    change, so provenance and attestability survive.
- **Unknown provenance fails closed (S2a):** a workflow without a block (written before S2a) is treated as `foreign_users` unless it is an unmodified built-in (hash match): never exportable, and it taints any version saved from it or any writer shown it.
- **Implemented in S2a (#229)** as `zebra_agent/provenance.py` + `WorkflowLibrary.save()`
  (OpenSpec `commons-provenance`). The owner is S1's `commons_owner_user_id`, else the routine
  owner; while no owner is known any user's runs set `foreign_users` (fail closed).
- **Migration:** existing workflows gain the block on their next save, and their definition id
  moves to the `c:` form then (S2b: the loader derives it whenever the block has a hash). Metrics key
  on workflow name, so history is kept, and old definitions stay in the store, so in-flight
  processes resume.

**Export and adoption (S2b) as built (#229, OpenSpec `commons-export`).**
- **Ids:** `zebra.definitions.loader` uses `c:` + sha256(`content_sha256:name`)[:16] when the
  `commons` block has a hash, else `sha256(name:version)`.
- **Export file** (`zebra_agent/commons/export.py`): canonical JSON
  `{format: "zebra-workflow-export", version: 1, event, chain}`. `event` is kind 31229
  (provisional) signed by the **device** key, tags `x` (hash), `zebra` (publisher Zebra pubkey),
  content `{name, yaml, commons}` with the YAML's block and local tags removed; `chain` holds the
  signer's `DEVICE_CERT`s. `verify_export` needs the exact bytes `dump_export` wrote (so any changed
  byte fails), lowercase hex ids/keys/sigs, every chain event a valid cert of the signer from the
  Zebra, `verify_attributed` against the chain plus the certs and revokes the verifier holds (a held
  revoke rejects; without relays a revoke made elsewhere is unknown), `x` = block hash = the hash
  recomputed from the YAML, and `foreign_users: false`. `export_workflow` refuses unless
  `commons_exportable` and the device is certified. Web: `api/commons_export.py`,
  `manage.py commons_export NAME [--out F]` and `commons_import F [--expect-zebra NPUB] [--adopt]
  [--name N]` (needs `COMMONS_ENABLED`; adopting at the command line is the owner's approval).
- **Adoption:** `WorkflowLibrary.save(yaml, writer="adopt", received=block, expected_sha256=hash,
  name=, origin_pubkey=)` (`provenance.adopted_block`): hash of the YAML = block hash = offered hash,
  block `foreign_users: false`; keeps the block verbatim except `sphere` (local), `share_with: []`,
  `adopted_at`, `supervised: true`, `origin_pubkey` if absent; drops received local tags, never adds
  `llm-defined`; refuses a name taken by a different active workflow (no shadowing `_N` copy),
  returns the existing file for a re-adopt of the same hash. Raises `AdoptionRefused`.
- **`sharing` domain:** in `DEFAULT_DOMAINS`; `OWNER_GOVERNED_DOMAINS = {"sharing"}`: the trust gate
  reads the owner's level and freed status (`__workflow_library__.refresh_owner()`), whoever the
  process runs for, and routes `approve` with no owner.
- **`commons_pii_scan`** (`zebra_tasks/commons/pii_scan.py`): rules (emails outside reserved example
  domains, phone, Luhn card, UK NI, postcode, non-loopback/non-documentation IPv4, common secret
  formats, URLs with credentials; `{{templates}}` ignored) then a low-tier `complete_json` call over
  every string of the workflow (keys and values, no `commons` block) and the golden tasks. Routes
  `clean` / `rejected`; findings are masked. Fails closed (`failed_closed: true`) on bad YAML, more
  than `max_chars` (60000) of text, no LLM, a provider error or a reply without a boolean
  `personal_data`. `always_reversible`: reads plus one LLM call. The workflow text goes to the LLM
  provider like every LLM-written workflow already does; the scan guards the wider audience.
- Attestations and outcome reports are only ever published for a workflow whose current hash equals
  the offered hash. Runs of a locally modified copy never count against the publisher.

**Judged import and supervised use (S3) as built (#230, OpenSpec `commons-import`).**
- No relays yet: the import takes a signed export file (S2b), now optionally carrying signed
  `display_name` and `golden_tasks`. The owner uploads it on `/commons/` (or `manage.py
  commons_import F --judge`); `commons_judge_import` stands in for the reputation step and does
  validation + registry check. Rejections are recorded on the run (`commons_import_result`,
  stage + reason), not attested.
- Gym import mode scores only the candidate against a pass mark (`pass_score` 0.6), since there
  is no local version to regress against.
- Supervised use is a generated *Supervised run* wrapper process created by
  `create_library_process` when `check_launch` says so, not a check inside
  `execute_goal_workflow`: every entry point then parks on the same owner-only approval with no
  change of its own. A rejected goal run routes `supervision_rejected` back to the selector with
  the workflow excluded. Approved-run counts are local (`.lineage/supervision.json`).
  `supervision_for` exempts no name: the wrapper is created directly, never through
  `check_launch`, and `Supervised run: …` is a reserved name the judge and the adopt save refuse.
- Every safety check sees every action the engine runs: task `action`, task and process-level
  `construct_action` / `destruct_action` (`definition_actions()`): strict and gate
  `unsafe_reason`, the judge's registry check and the action list the owner approves.
- Stops: the kill switch and `COMMONS_ENABLED` off refuse imports, adoption and supervised
  launches; the emergency override re-supervises every adopted workflow.

### Commons cache (S4–S7, Django models)

| Model | Purpose |
|---|---|
| `CommonsEventModel` | A verified copy of every Commons event this Zebra relies on: `event_id`, `kind`, `pubkey`, `created_at`, `relay_seq`, `content` (JSON), `sig`. Append-only. It is the local mirror. **Built in S4 (#231)**: table `zebra_commons_events` (migration 0034) with the full NIP-01 `event` JSON too (re-verifiable); `save` of an existing row, `update()` and `delete()` raise. |
| `PeerModel` | A known Zebra: `pubkey`, `display_name`, `vouched_by_user` (bool), `local_trust` (computed), `last_seen`. |
| `TrustEdgeModel` | The latest edge per (`from_pubkey`, `to_pubkey`): `weight` (-1..1), `reason`, `event_id`. |
| `WorkflowOfferModel` | One per content hash: `content_sha256`, `name`, `summary`, `stats`, `publisher_pubkey`, `status` (`seen` / `judging` / `adopted` / `rejected` / `delisted`), `judgement` JSON. **Built in S5 (#232)**: table `zebra_workflow_offers` (migration 0035) with `use_when`, `event_id`, `offered_at`; transitions enforced by `zebra_agent/commons/offers.py`; `judgement` is local (stage, label, voice, the gate's recorded reason, process id) and never published. |
| `MarketStateModel` | A rebuildable projection of the replayed ledger: balances per pubkey, holdings per (pubkey, hash), price per hash, the last `relay_seq` applied. |

All rows carry `user_id` per REQ-USR-002. Commons state is per instance, so it uses the instance's
default user.

---

## 3. API / interface changes

### Event kinds
All events are standard Nostr events (NIP-01), tagged `["t","zebra-commons"]` and a protocol version
`["v","1"]`. Kind numbers are **fixed in S4 (#231)** in one table, `zebra_agent/commons/kinds.py`:
each number ends in the slice that introduced it, addressable kinds sit in 30000–39999 and regular
ones in 1000–9999, none clashes with the NIP kind registry. Changing one is a protocol version
change (`v` 2). The relay write policies repeat the numbers; a test keeps them equal.

| Event | Kind | Public relay |
|---|---|---|
| `DEVICE_CERT` | 30228 (addressable) | yes |
| `DEVICE_REVOKE` | 1228 | yes |
| workflow export file | 31229 (never on a relay) | no |
| `OFFER` | 30231 (addressable) | yes |
| `ATTEST` | 1232 | yes |
| `TRUST` | 30233 (addressable) | yes |
| `GRANT` / `TRADE` / `OUTCOME` | 1234 / 1235 / 1236 | yes |
| `SKILL` | 4236 | no: private relay only |
| `RECEIPT` | 1246 | yes (operator key only) |

| Event | Kind type | Content and tags |
|---|---|---|
| `OFFER` | addressable (`d` = content hash) | `{name, summary, use_when, stats:{runs, success_rate, avg_rating, gym_score}, actions:[…], golden_tasks:[…], yaml}` · tags `x`=sha256, `zebra`=publisher Zebra pubkey, `parent`=sha256? (only a publicly offered parent) · signed by a device key, attributed by its `DEVICE_CERT`. `golden_tasks` are 1–3 sample goals with pass criteria, written by the publisher and scanned for personal data like the YAML. They let an importer test the workflow. |
| `ATTEST` | regular | NIP-32 style: `L`=`zebra-commons`, `l`=`adopted\|rejected-ethics\|rejected-gym\|rejected-pii\|pii-found\|worked\|failed`, `x`=sha256, `zebra`=attesting Zebra, `{reason (fixed vocabulary), rating?}` |
| `TRUST` | addressable (`d` = target pubkey) | `{weight, reason}` · tag `p`=target pubkey |
| `GRANT` | regular | Vouch-and-stake for a newcomer: `{stake}` · `p`=newcomer |
| `TRADE` | regular | `{side:"buy"\|"sell", shares, max_cost}` · `x`=sha256 |
| `OUTCOME` | regular | `{result:"worked"\|"failed"\|"ethics-rejected"\|"pii-found"}` · `x`=sha256, `e`=the reporter's `ATTEST adopted` event |
| `RECEIPT` | regular, signed by the Commons relay operator key | `{seq, event_id}`: gives the canonical replay order |
| `DEVICE_CERT` | addressable (`d` = device pubkey), signed by the Zebra key | `{label, sphere, observed, expires_at?}` · `p`=device pubkey. Published to both relays. |
| `DEVICE_REVOKE` | regular, signed by the Zebra key | `{reason}` · `p`=device pubkey. Published to both relays. |
| `SKILL` | regular, **private relay only** | NIP-44 encrypted **only to the certified devices of the spheres listed in the workflow's `share_with`**, one copy per device. Devices in other spheres, e.g. an observed work laptop for a home-only workflow, never receive a decryptable copy. Plaintext: `{yaml, commons block incl. ancestors, stats, sending_device}`. |

**Hard filter:** the publisher refuses to send any event to a public relay unless its kind is on the
public list, and refuses to send `SKILL` anywhere but the private relay. Built in
`CommonsClient.check_publish` (#231): every client applies it, a public client (`private=False`)
also refuses any event not tagged `zebra-commons`, and the public relay's write policy repeats it.

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
- `commons_adopt` and `commons_supervised_run` trust no process property: each refuses unless it runs in its own system workflow (the shipped *Commons Import*, the regenerated *Supervised run* wrapper) and the step journal records the gates / the owner's answer. Imported and generated workflows may not use the Commons-internal actions (`zebra_tasks/commons/guard.py`).
- `commons_adopt`: `WorkflowLibrary.save(..., writer="adopt")` keeps the received `commons` block verbatim (hash verified), sets `supervised: true` and renames for display

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
    candidate PROMOTED (`gym.py:265`) and must not be reused as-is.
  - It runs **only `always_reversible` actions** (strict `unsafe_reason`, S0 #245). Today's gym
    blocks only `always_irreversible`, and actions with no hint default to `context_dependent`, so
    `file_delete`, `file_write`, `python_exec`, `subworkflow`, `queue_goal` and memory or values
    writers would run on the publisher's own golden goals before any human saw the workflow. An
    import using any other action skips the gym and escalates to a human.

### Web UI
- `/commons/` lists:
  - this Zebra's public key
  - peers and trust
  - offers seen, adopted and rejected, with Zebra's reasons in its own voice
  - market prices and holdings (S7)
- Human vouching: "I know this Zebra" on a peer, which sets `vouched_by_user` and publishes `TRUST`.
- **Built in S5 (#232)**: the "Public Commons" section (`partials/commons_offers.html`): offers seen (status, publisher npub and fingerprint, stats, worked / failed / adopted / rejected counts, Zebra's verdict as a fixed first-person line plus the gate's recorded reasoning), this Zebra's own offers with other Zebras' attestations, owner-only **Import this**; empty states while publishing is off. Peers and trust: **built in S6 (#233)**, the "Zebras I know" section (`partials/commons_peers.html`).

### Genealogy view
A family tree of skills, in two views built from data Zebra already keeps:
- `commons.ancestors`, `parent_sha256` and `fork_of`
- the writer recorded by `WorkflowLibrary.save()`
- leak-guard results
- `SKILL`, `OFFER`, `ATTEST` and `GRANT` events

- **Private genealogy** (`/workflows/<name>/genealogy/`): visible only on this device and never
  published. The lineage of one workflow as a DAG. Each version shows:
  - hash, date, the device and sphere it was made on
  - the writer: creator, variant, optimizer, human, adopted or synced
  - what changed: a diff to its parent, with the reason in Zebra's own voice ("I added a review
    step after three failed runs at work")
  - leak-guard hits that were generalised or rejected, and `tainted_by`
  - per sphere: shared, waiting for approval, never proposed (sensitive) or blocked
  - forks waiting for a choice, and retired versions
  Versions that exist only in another sphere appear only if they were shared here. A device can't
  see what it was never sent.
- **Implemented in #238 (private):** writer, time, sphere, device, reason and leak-guard status
  live in a local journal (`<library>/.lineage/journal.jsonl`, `zebra_agent/genealogy.py`), not in
  the `commons` block, so they never ship with an export. Reasons are only the evaluator's
  rationale (optimizer, gym) or the selector's voice / reasoning (creator, variant); a human save
  has none. Hit text is never journaled. Per-sphere share status and forks show empty states
  until S3b-1 (#236). Spec: `openspec/specs/workflow-genealogy/spec.md`.
- **Public genealogy** (`/commons/genealogy/`): built only from public events.
  - **Workflow lineage across Zebras:** offers linked by `parent`, who published each, how many
    Zebras adopted it, attestations (worked, failed, rejected and why), and the market price over
    time (S7).
  - **Zebra lineage:** who vouched for whom (`GRANT` events), and this Zebra's trust paths ("I trust
    B through A: 0.8 × 0.6").
- **Privacy rule:** an `OFFER` names a `parent` only if that parent was itself publicly offered.
  Private ancestors are never referenced publicly, not even by hash. So the public tree starts at
  the first public version.
- **Rendering:** server-rendered (Django templates + inline SVG, layered DAG layout) using the
  tokens and voice rules in [web-ui-design.md](web-ui-design.md). No new JS framework.

### Infrastructure
- `strfry` relay as a Quadlet unit on the prod host, rootless Podman, a few MB of RAM, behind the
  existing reverse proxy on `wss://…/commons`. It accepts only events tagged `zebra-commons`.
- The operator key signs `RECEIPT`s.
- The private sync relay (S3b-2, #246) is a second strfry on `wss://…/sync` (loopback
  `127.0.0.1:7778`), with its own write policy, receipt sidecar and operator key; files in
  `deploy/podman/sync-relay/`, installed by hand ([commons-sync-relay-runbook.md](commons-sync-relay-runbook.md)).
- Mirroring to 2–3 public relays is configured in `ZEBRA_COMMONS_RELAYS`.
- **Built in #231 (not deployed):** `deploy/podman/commons-relay/` (strfry Quadlet on loopback
  `7779`, config without NIP-42, public-kinds write policy, receipt sidecar, network); installed by
  hand ([commons-public-relay-runbook.md](commons-public-relay-runbook.md)), route
  `wss://<host>/commons` (exact path; `/commons/` stays the web page).

---

## 4. Control flow

### Offer
1. The dream cycle (S8) or a human picks a learnt workflow with enough runs (≥ `MIN_RUNS_TO_OFFER`).
2. `commons_offer` runs. A personal-data or ethics failure ends it with the reason recorded. Under
   SUPERVISED, the `trust_gate` makes it a human task showing the YAML and the summary.
3. The `OFFER` is published. In S7 it is followed by an opening `TRADE` buy (publisher stake).

**Offers (S4) as built (#231, OpenSpec `commons-offers`). Code only, off by default.** Owner
steps: [commons-public-relay-runbook.md](commons-public-relay-runbook.md).

- **Start:** `manage.py commons_offer NAME` starts *Commons Offer* (`commons_offer.yaml`, system)
  as the owner, or the dream cycle (S8, #235, below).
- **Steps:** `commons_prepare_offer` (preconditions; canonical YAML via `relabel`, its hash, stats
  from the `MetricsStore` incl. the gym mean, the actions, one low-tier `complete_json` that sees
  only the YAML and numbers and writes `summary`, `use_when` and 1–3 golden tasks, the library's
  own golden tasks preferred) → `commons_pii_scan` over the YAML and everything else published
  (golden tasks, summary, use_when; fails closed) → `ethics_gate` (plan_review; `escalate` → owner)
  → `commons_offer_route` → `trust_gate` (`sharing`, owner-governed) or the owner's approval
  (`owner_only`) → `commons_offer_record` → `commons_publish` → `commons_record_offer`
  (`commons_offer_result`: `published` / `refused` / `declined`, stage and reason).
- **Preconditions (all fail closed with a recorded reason):** `commons_exportable` (not protected,
  no `foreign_users`, has a block); the leak guard not `kept` / `error` on the version or an
  ancestor (`leak_kept`); ≥ `MIN_RUNS_TO_OFFER` (5) recorded runs; not already offered; a
  publisher configured; the Commons not stopped. Checked at prepare and again at publish.
- **`public` in `share_with`:** the workflow is the public suggest-and-approve step. Approval calls
  `library.approve_share(name, "public", hash)` and journals a `share` record (sphere `public`);
  `commons_publish` refuses unless `public` is in the current version's `share_with`, so a save
  after approval voids it. Observed taint (a `tainted_by` sphere a cert marks observed, or one no
  cert describes) routes to the owner, never to the trust gate, and an unattended approval
  re-checks it.
- **What is published is what was scanned:** `commons_offer_record` and `commons_publish` run only
  in the shipped workflow (`guard.is_offer_workflow`), take the offer from the step-journal entry
  of `prepare` and check the journal for the gates and the owner's answer.
- **Publisher** (`commons/publisher.py`, `extras["__commons_publisher__"]`): the canonical relay
  (first of `COMMONS_RELAYS`) and mirrors, all public clients. It publishes the signing device's
  `DEVICE_CERT` and the Zebra's revokes (never other devices' certs), then the `OFFER`
  (`commons/offer.py`: `build_offer`, `verify_offer`, `public_parent`); mirrors are best effort.
  It waits briefly for the operator's receipt (`COMMONS_RECEIPT_PUBKEY`); the daemon tick's
  `refresh_receipts()` picks up late ones. Every event and receipt goes into the local mirror
  (`CommonsEventModel`, append-only, `user_id` = owner; `CommonsMirror` interface).
- **Public relay** (`deploy/podman/commons-relay/`, not deployed): a second strfry on loopback
  `7779`, no NIP-42, write policy accepting any Zebra's `zebra-commons` events of the public kinds
  (`OFFER` needs `d` = `x` and one `zebra` tag), never `SKILL` or NIP-70 protected events,
  `RECEIPT` only from the operator key; journals each event for the same receipt sidecar
  (`--secret-env ZEBRA_COMMONS_OPERATOR_SECRET`).

### Import
1. A subscription to the Commons relay receives `OFFER`s and stores them as `WorkflowOfferModel(status=seen)`.
2. Candidates are offers whose summary matches a capability gap (the selector found no good workflow,
   or a continuation reported `new_workflow`) and whose **import score** clears the threshold:
   `score = α·local_trust(publisher) + β·norm(market_price) + γ·attestation_signal`,
   where `attestation_signal` is the trust-weighted mean of `worked` minus `failed` reports.
   While the market is parked, β = 0.
3. `commons_import` runs. Any gate rejecting publishes an `ATTEST rejected-*`. Adoption publishes `ATTEST adopted`.
4. **Supervised use**, enforced *outside* the workflow. `trust_gate` is a task inside workflow YAML,
   and an imported workflow's YAML is the publisher's, so it can't be relied on to gate itself.
   - `execute_goal_workflow` (`zebra-tasks/zebra_tasks/agent/execute_workflow.py`), part of the
     trusted main loop, checks `commons.supervised` on the selected workflow **before** starting the
     child process.
   - If it is set, it raises a human task: "Run imported workflow X for this goal?", listing the
     actions it uses and flagging irreversible ones (via `reversibility_hint`).
   - Rejecting fails the goal over to the next selector choice.
   - The flag clears after `SUPERVISED_RUNS` approved, successful runs, or when a human clears it.
   - The check lives in **one launch choke point** (S0 #245) that every start of a library workflow
     goes through: goals (`execute_workflow.py`), `loop.py`, `direct_run.py`, scheduled routines
     (`scheduler/loop.py:162-176`) and `subworkflow` / `parallel_subworkflows` children. A test
     proves nothing starts a library workflow around it.
5. After each run, `ATTEST worked|failed` is published. In S7, an `OUTCOME` is published too.

**Offers in, attestations out (S5) as built (#232, OpenSpec `commons-attestations`). Code only,
off by default.** Second-Zebra check: [commons-public-relay-runbook.md](commons-public-relay-runbook.md) §7.

- **Exchange** (`commons/exchange.py` `CommonsExchange`, `extras["__commons_exchange__"]`): built
  only alongside the publisher, so with `ZEBRA_COMMONS_RELAYS` unset nothing is fetched or attested.
- **Step 1, intake**: each daemon tick (`publish_tick` → `exchange_tick` → `poll()`) fetches
  `OFFER`s since the last poll, the publishers' certs / revokes and the operator's receipts, and
  stores an offer only when `verify_offer` accepts it (signature, `DEVICE_CERT` attribution,
  receipt-ordered revocation, hash). One `WorkflowOfferModel` per hash (duplicates ignored), own
  offers skipped; a revoked publisher device delists `seen` offers (only when the row's own
  `OFFER` event fails, never a third party's copy of the same hash). Mirrored in `CommonsEventModel`.
- **Step 2, candidates**: not in S5. The owner chooses: **Import this** on `/commons/`
  (`start_offer_import`): `seen` / `rejected` → `judging`, *Commons Import* on the mirrored offer.
- **Step 3, judged import of an offer**: `commons_import.yaml` v2 takes `offer_event` (the `OFFER`
  + certs, `offer_input`); `offer_as_export` turns it into the same `ExportVerification` as a file
  (received block: hash, public parent, `origin_pubkey`, `foreign_users: false`), so every gate is
  unchanged; judge and adopt both re-verify. The last step, `commons_attest_import`, reads the
  outcome from the step journal and moves the row: `adopted` → `ATTEST adopted`; the
  personal-data scan → `pii-found` (findings) or `rejected-pii` (failed closed); ethics →
  `rejected-ethics`; gym → `rejected-gym`. Judge rejections, the owner's "no" and refused
  adoptions are local (not about the workflow) and never attested; neither is any file import.
- **Step 5, runs**: `assess_and_record` → `exchange.after_run(library, name, success)` attests
  `worked` / `failed` only when the workflow is an adoption whose row is `adopted` and the hash of
  its current YAML equals the offered hash: a locally changed copy never attests.
- **`ATTEST` shape** (`commons/attest.py`): tags exactly `L`, `l` (label + namespace), `x`,
  `zebra`, `t`, `v`; content `{reason, rating?}` with `reason` from a fixed table per label and
  `rating` 1–5. No free text exists in the API, so goal text, outputs, names and LLM text cannot
  reach an attestation; `verify_attest` refuses anything else. Readers filter by `#x`.
- **Counts**: `adopted` / rejections are distinct Zebras, `worked` / `failed` are events (trust
  weighting is S6). Two identical attestations in the same second share an id and count once.

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
   - Under an earned `sharing` trust level, Zebra may skip the approval only when the target sphere
     is not `observed` **and** `tainted_by` holds no `observed` sphere. So work data never leaves
     work, and nothing reaches the work laptop, without a human approving.
   - These observed-sphere approvals are a dedicated human task (`observed_share_approval`), **not**
     `trust_gate`. Freeing Zebra (REQ-TRUST-006) makes every trust gate pass through
     (`trust_gate.py:153-163`), but these approvals protect third parties and the human's privacy
     from an observer, not oversight of Zebra. Freeing does not remove them.
1. **Send.** A device sends a `SKILL` event only for workflows whose `share_with` names the target
   sphere. The event goes to the private relay, encrypted only to the certified devices of the
   spheres in `share_with`.
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
3. **Merge by lineage.** Workflows are content-addressed, and each version carries its last
   `ANCESTOR_WINDOW` (32) ancestor hashes in `commons.ancestors`. So a receiver can place a version
   even if it never saw the intermediate saves, and merging works like git:
   - The same hash is already present: no-op.
   - The incoming workflow descends from the local one (the local hash is in the incoming
     `ancestors`): fast-forward and replace.
   - The local one descends from the incoming one: ignore it (stale).
   - Neither descends from the other (forked at home and at work, or the lineage is longer than the
     window): a **fork**.
     - The incoming version is saved under a distinct name, `<name> (from <sphere>)`, with
       `commons.fork_of` set on both copies.
     - A human task asks which to keep, showing the diff.
     - The library's "newest file wins" lookup (`library.py:413-430`) and the curator's
       `SUPERSEDED_COPY` rule (`curator.py:259-274`) resolve by lineage, and skip workflows with
       `fork_of` set. A fork is never retired automatically.
   - **Re-approval rule** (send side): every content change resets `share_with` (see the provenance
     section), so no new version reaches another sphere on an earlier approval. Example: a work
     workflow approved for home, later re-optimised at work with fresh work runs, is a new share
     decision with the diff shown. That holds even though `tainted_by` was already `[work]`.
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

**Skill sync (S3b-1) as built (#236, OpenSpec `commons-skill-sync`).** Over an in-memory
transport only; the relay, NIP-44 and receipts are #246.
- `zebra_agent/commons/client.py`: `CommonsClient` ABC plus `InMemoryRelay` /
  `InMemoryCommonsClient`. `check_publish` (the hard filter) refuses `SKILL` (provisional kind
  4236) on any relay that is not private.
- `skill.py`: one event per recipient device (certified, unrevoked, sphere in `share_with`, never
  the sender), signed by the sending device, `p`-tagged, plaintext with `["enc","none"]` until
  NIP-44. The receiver accepts only its own Zebra's devices and reads the sender's sphere from its
  cert, never from the event body; its own sphere must be in the sent `share_with`.
- `sync.py` `SyncService` (`extras["__commons_sync__"]`) proposes, sends and merges. Share
  decisions are `share` records in the #238 journal per (hash, sphere), so each version is asked
  about once and the genealogy shows each sphere's status.
- System workflows `skill_share.yaml` and `skill_receive.yaml` hold the gates and human tasks
  (`share_approval`, `observed_share_approval`, `receive_approval`, `fork_choice`). A sensitive
  workflow for an unobserved sphere is still asked about, with no autonomy skip.
- A received workflow keeps its sent `supervised` (same Zebra, normal trust); fast-forward
  retires the old file; a fork is `<name> (from <sphere>)` with `fork_of` on both copies.
- Leak-guard taint (journal) blocks a version from being proposed or sent: a `saved` record
  whose writer status or save-time check (`save_check`) is `kept` or `error` taints that hash
  and every descendant (`ancestors` / `parent_sha256`), since the guard never re-flags a literal
  already in the parent. A version with no `saved` record (written before the #238 journal, when
  `kept` lived only in process output, or the journal was lost) is tainted too, unless it is an
  unmodified built-in; so is one with an unrecorded, non-built-in ancestor, unless a version in
  its lineage arrived by sync (the sending device checked those ancestors). There is no way to
  clear it yet; a clean rewrite starts a new lineage.
- Triggers: `assess_and_record` calls `SyncService.after_run` after recording a successful goal
  run (proposed at `MIN_RUNS_TO_SHARE` successes); `AgentLoop.run_dream_cycle` calls
  `after_dream`. Both only when `extras["__commons_sync__"]` is set and never fail the run.
- `SyncService.direction` defaults to `ZEBRA_SYNC_DIRECTION` (`both`; an unknown value is `off`).
- `skill_share_prepare` records `proposed` only when it routes `propose`; a skip is `skipped`
  (or `blocked` for leak taint) and a failed process `failed`. Neither of those is a decision,
  so Zebra may ask again later; the genealogy shows "not proposed" / "share failed".
- Not yet: a Share button on the workflow page
  (`start_share(manual=True)` exists).

**Skill sync (S3b-2) as built (#246, OpenSpec `commons-sync-relay`). Off by default.** Owner
steps: [commons-sync-relay-runbook.md](commons-sync-relay-runbook.md).
- Transport: `commons/nostr.py` is the only importer of `nostr-sdk` 0.45 (alpha; abi3 wheels work
  on CPython 3.14 aarch64): `NostrSdkTransport` (NIP-42 by the device key; sets
  `uniffi_set_event_loop` before each call, rebuilds the client after an outage, always shuts it
  down) and NIP-44 v2. `commons/relay.py`: `RelayCommonsClient` over a `RelayTransport`
  (`send` / `query`), re-verifies every fetched event, polls for `subscribe`, and queues publishes
  in `Outbox` (`<library>/.sync/outbox.jsonl`, flock, fsync) while the relay is unreachable or
  answers a transient refusal; `flush()` resends in order; `blocked:` / `invalid:` /
  `restricted:` raise `PublishRefused` (queued ones move to `outbox.rejected.jsonl`).
- `SKILL`: NIP-44 ciphertext to its one recipient device, `["enc","nip44"]`, NIP-70 `["-"]`;
  plaintext is rejected (`not_encrypted`), a wrong key `not_decryptable`; over 65535 bytes is
  refused at build time.
- strfry 1.1.3 asks for NIP-42 AUTH only for NIP-70 protected events and has no read restriction,
  so: `SKILL`s are protected and the write policy accepts one only when `authed == pubkey` and that
  device holds a valid, unrevoked cert from a registered Zebra key; certs and revokes are accepted
  by author (a registered Zebra key; strfry checks signatures); reads are open (ciphertext, but
  sender / recipient / timing and cert labels are visible).
- Receipts (`commons/receipts.py`, `RECEIPT` kind 1246, provisional): the write policy
  (`deploy/podman/sync-relay/write_policy.py`, stdlib, in the strfry container) gives each
  accepted event the next `seq` and journals it before accepting; the sidecar
  (`python -m zebra_agent.commons.receipts`, operator secret only from
  `ZEBRA_SYNC_OPERATOR_SECRET`) signs `{seq, event_id}` (tags `e`, `k`, `seq`) per journal line.
  `receipt_order()` keeps receipts signed by `SYNC_RECEIPT_PUBKEY` whose content matches the tags.
- Revocation: `verify_device_chain(..., receipt_seq=, event_id=)`; with receipts a revoked
  device's event passes only with a receipt `seq` below every revoke's (no receipt:
  `no_receipt`; a revoke without one: `revoked`); without receipts the S1 rule. Recipient choice
  never uses receipts.
- `SyncService`: `receipt_pubkey`, `receipts`, `refresh()` (this Zebra's certs and revokes from
  the relay, receipts for revokes and for events of revoked senders; never raises),
  `publish_identity()`, `flush()`, `merge_certs()`; `send` refreshes and publishes identity first;
  `receive_pending` refreshes with the pending events.
- Web: `api/commons_sync.py` `build_sync_service()` (Commons on + `SYNC_RELAY` + identity + device
  key, else None; direction is the stricter of `ZEBRA_SYNC_DIRECTION` and the stored one) and
  `sync_tick()` (daemon: DB certs, flush, refresh, identity, receive; each step logged, never
  fatal). nostr-sdk is never imported while sync is off.
- Infrastructure in `deploy/podman/sync-relay/` (not deployed): strfry Quadlet (pinned digest,
  `127.0.0.1:7778`), `strfry.conf`, `write_policy.py`, `allowlist.json.example`, receipt sidecar
  Quadlet, `zebra-sync.network`, 90-day retention service + timer (`SKILL`s and their receipts;
  certs, revokes and their receipts are kept).
- Tests: `test_commons_relay.py`, `test_sync_relay_policy.py`, the web wiring, and
  `test_sync_relay_integration.py` (throwaway strfry container; skips without podman or the image
  and in CI unless `ZEBRA_SYNC_RELAY_IT=1`).

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

**Shipped (#237)**, with these refinements (details in `specs/zebra-as-is.md`, Dream cycle):
- The exposure set is the raw run texts, not the evaluator's findings: the evaluator records what it
  was shown (`run_exposure`), so implementing a suggestion verbatim is not a hit, while a specific
  the findings copied from a run still is.
- The writer's own goal counts only 8-token copies as phrases (a workflow describes its purpose);
  all-caps acronyms (SLA, API) are not names.
- The second hit rejects in the dream-cycle optimizer only. The creator and variant creator keep
  the rewrite and record the hits (`leak_guard.status: kept`), so a user's goal never fails over its
  own words; that data already lives in the sphere's runs. S3b's scans must treat `kept` as tainted.
- Step 5 (`tainted_by`) waits for the `commons` block (S2, #229).

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
- Every later dream-cycle change resets `share_with`, so an earlier "share with home" approval
  never carries a new version home. This holds even when the workflow originally came from home.
- Work is `observed`, so neither earned `sharing` autonomy nor freeing Zebra removes that approval.
- The optimizer saves through `WorkflowLibrary.save()`, so the leak guard and the `commons` block
  can't be bypassed.
- **Result:** customer details stay out of the workflow, and the work version never goes home
  without your approval.

**B. "At home I plan applying for a new job, and Zebra creates workflows for it. Does that sync to
my work machine?"**
- The creator writes "Job application tracker" at home: `sphere: home`, `share_with: []`.
- The leak guard keeps company names and CV details from your goals out of the YAML.
- When Zebra considers sharing it with work, the sensitivity check flags job searching as sensitive
  for an `observed` sphere. Zebra **never proposes it**, and no `SKILL` event is sent.
- Only an explicit human share, past the "visible on a managed device" warning, could send it.
  Freeing Zebra doesn't remove that step.
- Workflows shared only with other spheres are never encrypted to work devices. So even a
  home-to-home share isn't decryptable on the work laptop.
- **Result:** it doesn't reach the work machine, not even its name.

**Private relay:** a second strfry Quadlet on the prod host, separate from the public Commons relay.
- NIP-42 authentication. Keys that may read or write:
  - **Zebra keys** on the relay's allow-list, registered when the human enables sync (the operator
    controls who may use the relay). This lets the first `DEVICE_CERT` and every `DEVICE_REVOKE` be
    published.
  - Device keys with a valid, unrevoked `DEVICE_CERT` from an allow-listed Zebra key.
- It accepts only `SKILL`, `DEVICE_CERT` and `DEVICE_REVOKE`.
- Its own operator key (`SYNC_RECEIPT_PUBKEY`) signs a `RECEIPT {seq, event_id}` for every stored
  event. Revocation ordering uses these receipts, not `created_at`.
- Retention is 90 days: devices keep their own copies, and offline devices catch up within that
  window or by re-pairing.
- The work device only needs outbound `wss://`.

### Web of trust (S6)
- Direct trust comes from the human (vouching, about 0.8) and from experience: an EWMA over this
  Zebra's own attestations of that publisher's workflows.
- Transitive trust: `t(me→Z) = max over paths p of ∏ weights`, with path length ≤ 3, a decay of 0.9
  per hop, and negative edges not propagated past one hop. It is recomputed after new edges arrive.
- Sybil limit: Zebras with no path from a human-vouched seed have trust 0, whatever they publish.

**Web of trust (S6) as built (#233, OpenSpec `commons-web-of-trust`). Code only, off by default.**
Live check: [commons-public-relay-runbook.md](commons-public-relay-runbook.md) §8.

- **`TRUST`** (`commons/trust.py`): signed by a certified device key (devices do not hold the Zebra
  key), tags exactly `d` = `p` = target, `zebra` = truster, `t`, `v`; content `{reason, weight}`
  (2 places). Reason: `vouched` / `withdrawn` / `distrusted` / `experience`, or the owner's note
  (≤ 140 chars, published as typed). Self-trust is refused. Latest edge per pair: receipt order,
  else `created_at` (ties: higher id); own changes are strictly later than the last one.
- **Paths**: hops = edges, first hop to a human-vouched seed, value `∏ weights × 0.9^(hops-1)`, so a
  vouch is 0.8 and "B via A" 0.8 × 0.6 × 0.9 = 0.432; ≤ 3 hops; negative edges only as the last hop;
  this Zebra's own negative edge wins over any path, and a Zebra it distrusts is never a hop (its
  vouches pass nothing on); its own positive edge counts only to a Zebra a
  seed path reaches. Ties: fewer hops, then the smaller path.
- **Experience**: EWMA rate 0.2 on this Zebra's own `ATTEST`s (worked +1; failed, rejected-ethics,
  rejected-gym, pii-found -1; adopted and rejected-pii nothing); the owner's vouch is a floor and a
  distrust a ceiling; published at a 0.1 change from the last published weight (`publish_pending`
  retries each tick). Owner changes are `pending` until a relay accepts them and are always
  retried, whatever the threshold.
- **Concurrency**: all `WebOfTrust` mutations run under one lock, and peer writers touch only their
  own columns, so a recompute can never undo an owner's vouch or distrust.
- **Import score**: α = 0.7, γ = 0.3, β = 0; `attestation_signal` counts only reporters with positive
  local trust, never the publisher or this Zebra. Below 0.5 an offer is never judged automatically
  (S8) and **Import this** shows the score with a warning (the owner may still import).
- **Stores / UI**: `PeerModel` (+ `owner_weight`, `best_path`), `TrustEdgeModel` (+ `created_at`,
  `relay_seq`, `published_weight`); `/commons/` "Zebras I know" section. Without
  `ZEBRA_COMMONS_RELAYS` the owner's vouches are kept locally and nothing is fetched or published.

**Dream cycle (S8) as built (#235, OpenSpec `commons-dream`). Code only, off by default.**

- `commons_dream` (`zebra_tasks/commons/dream.py`), a step of `dream_cycle.yaml` (v10) before the
  summary. Without a publisher (`ZEBRA_COMMONS_RELAYS` unset) it records "Commons off" and does
  nothing; it never fails the cycle. It only starts the existing gated workflows; trades are out
  while the market is parked.
- **Offer step 1**: learnt workflows (exportable, not a shipped built-in, not adopted) with
  ≥ `MIN_RUNS_TO_OFFER` runs and good stats (success rate ≥ 0.8, rating ≥ 4.0 when rated) that pass
  `offer_refusal`, not offered, not already open or asked about at this hash → *Commons Offer*
  (the public suggest-and-approve step; `proposed` journalled), ≤ 1 per cycle.
- **Import step 2**: gaps (`creator` saves in the window, `new_workflow` continuations) matched to
  `seen` offers by keyword overlap; import score ≥ 0.5 → *Commons Import* in the background,
  ≤ 1 per cycle, within a daily import budget (USD, spend ledger over the import trees, UTC day).
  Below the threshold the offer is skipped with its score and never judged automatically.
- **`sharing` promotion**: after 5 owner share approvals in a row without a note (declines and
  notes restart the count) since the last `sharing` suggestion or level change, a pending
  suggestion one level up (REQ-TRUST-004); never self-promotes.
- **Report**: `commons` (voice lines, offers proposed, imports started, skipped reasons, budget,
  promotion), in the summary and a "Commons" block on `/dreams/`.

### Reputation market (S7, parked)
> Parked as its own later theme (decision b; #234, `phase::19-reputation-market`). Until then the
> import score is `α·local_trust + γ·attestation_signal`, with no market term, and the dream cycle
> proposes no trades. Kept here as the starting design for that theme.

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
- **Points supply.** Exactly three rules create points and three destroy them. Nothing else changes
  total supply, so every implementation computes the same balances.
  - *Mint: genesis.* Protocol v1 pins a `GENESIS` list of (Zebra pubkey, balance), e.g. the founding
    Zebra(s) at 1000 points. It is applied before the first receipt, so the market can start. Adding
    a genesis entry is a protocol version change, not a local setting.
  - *Mint: `GRANT`.* A voucher locks `GRANT_STAKE` (50) of its own balance and mints
    `GRANT_AMOUNT` (100) for the newcomer.
    - A voucher may make at most `GRANT_MAX_PER_30D` grants (2).
    - It must have a balance of at least `GRANT_MIN_BALANCE` (150) and be at least
      `GRANT_MIN_AGE_DAYS` (30) old.
    - So a newcomer (100) can reach vouching rights by earning 50 or more from backing workflows
      that work. A fresh grantee can't vouch at once, which keeps Sybil chains slow.
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
| `COMMONS_KEY_DIR` | `ZEBRA_COMMONS_KEY_DIR` | `~/.zebra-agent/commons-keys` | Where the Zebra and device secret keys are kept (`FileCredentialStore`, 0600; prod volume `zebra-commons-keys`) |
| `COMMONS_RELAYS` | `ZEBRA_COMMONS_RELAYS` | — (unset: no publishing) | Public relays, comma- or space-separated; the first is canonical (receipts), the rest mirrors. Runbook suggests ours plus 1–2 public |
| `COMMONS_RECEIPT_PUBKEY` | `ZEBRA_COMMONS_RECEIPT_PUBKEY` | — | The relay operator key trusted for `RECEIPT`s |
| `SYNC_RELAY` | `ZEBRA_SYNC_RELAY` | — | The private relay for `SKILL` events. Unset means no device sync. |
| `SYNC_DIRECTION` | `ZEBRA_SYNC_DIRECTION` | `both` | `send` / `receive` / `both` / `off`, set per device (e.g. a work device that may only receive) |
| `SYNC_CONFIDENTIAL_PATTERNS` | `ZEBRA_SYNC_CONFIDENTIAL_PATTERNS` | — | Extra per-device regexes, such as codenames or domains, that block sending |
| `MIN_RUNS_TO_SHARE` | — | 2 | Successful runs before Zebra suggests sharing a workflow with another sphere |
| `ANCESTOR_WINDOW` | — | 32 | Ancestor hashes carried per version for lineage merges |
| `COMMONS_DREAM_ENABLED` | `ZEBRA_COMMONS_DREAM_ENABLED` | true | The dream cycle's Commons step (S8); inert without `COMMONS_RELAYS` |
| `MAX_OFFERS_PER_CYCLE` / `MAX_IMPORTS_PER_CYCLE` | `ZEBRA_COMMONS_MAX_OFFERS_PER_CYCLE` / `ZEBRA_COMMONS_MAX_IMPORTS_PER_CYCLE` | 1 / 1 | Offers / imports the dream cycle may start per cycle |
| `DAILY_IMPORT_BUDGET_USD` | `ZEBRA_COMMONS_DAILY_IMPORT_BUDGET_USD` | 0.50 | Daily (UTC) spend cap on dream-started imports, from the spend ledger |
| `COMMONS_OFFER_MIN_SUCCESS_RATE` / `COMMONS_OFFER_MIN_RATING` | `ZEBRA_COMMONS_OFFER_MIN_SUCCESS_RATE` / `ZEBRA_COMMONS_OFFER_MIN_RATING` | 0.8 / 4.0 | Stats a workflow needs before the dream cycle proposes offering it |
| `COMMONS_SHARING_PROMOTION_APPROVALS` | `ZEBRA_COMMONS_SHARING_PROMOTION_APPROVALS` | 5 | Unchanged owner share approvals before Zebra asks for `sharing` promotion |
| `SYNC_RECEIPT_PUBKEY` | `ZEBRA_SYNC_RECEIPT_PUBKEY` | — | Private-relay operator key trusted for sync receipts; unset keeps the S1 revocation rule |
| — | `ZEBRA_COMMONS_OPERATOR_SECRET` | — | Public relay's receipt sidecar only: its operator secret (a different key from the sync relay's); never `prod.env` |
| — | `ZEBRA_SYNC_OPERATOR_SECRET` | — | Receipt sidecar only: the operator secret (hex or nsec); a secret env file / CI variable, never `prod.env` |
| `SUPERVISED_RUNS` | — | 3 | Approved successful runs before an imported workflow runs without the pre-run approval |
| `MIN_RUNS_TO_OFFER` | — | 5 | Effectiveness evidence needed before offering |
| `IMPORT_SCORE_THRESHOLD` | — | 0.5 | Minimum import score to try judging (`commons/trust.py`, #233; with `VOUCH_WEIGHT` 0.8, `DECAY` 0.9, `MAX_HOPS` 3, `EXPERIENCE_RATE` 0.2, `PUBLISH_THRESHOLD` 0.1, α 0.7, γ 0.3) |
| `MARKET_LIQUIDITY_B` | — | 100 | LMSR liquidity |
| `GRANT_STAKE` / `GRANT_AMOUNT` | — | 50 / 100 | Vouching economics |
| `GENESIS` | — | founding Zebra(s), 1000 each | Initial balances pinned in the v1 ledger protocol |
| `GRANT_MAX_PER_30D` / `GRANT_MIN_BALANCE` / `GRANT_MIN_AGE_DAYS` / `GRANT_LOCK_DAYS` | — | 2 / 150 / 30 / 90 | Caps on point creation through vouching |
| `SETTLE_MINT` | — | 10 | Points minted per standing-weighted `worked` outcome |
| `DELIST_QUORUM` / `DELIST_MIN_STANDING` | — | 3 / 50 | Independent rejection attestations needed to delist |

Market parameters (`GENESIS`, `MARKET_*`, `GRANT_*`, `SETTLE_*`, `DELIST_*`) are part of the ledger protocol,
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
  every run, and imports start supervised. Judging runs only `always_reversible` actions; anything
  else waits for a human before it ever runs. Whether some actions (shell, code builder, outbound
  email) should be banned from imports even after approval stays open.
- **Several humans on one deployment.** Taint is per sphere, not per person, so decision a limits
  the Commons to the owner and blocks anything learnt from other users' runs. Per-user taint
  (`tainted_by_users` with each person's consent) is the upgrade path if households need it.
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
- **Open:** whether trust edges should be public or encrypted to their
  target (NIP-44); and whether humans should see each other's Zebras' public keys only, or a
  profile.

---

## Delivery slices (GitLab issues, each `Refs #41`)

Planned 2026-10-26 in waves. Slices in one wave are built in parallel, each in its own worktree,
then merged to master one at a time.

| Wave | Slice | Delivers | Depends on |
|---|---|---|---|
| done | #237 Leak guard | Exposure set per LLM writer, check on added literals before save, generalise-or-reject, optimizer prompt rule | — |
| 1 | #245 S0 Safety prerequisites (**shipped**: `zebra_tasks/launch.py`, `unsafe_reason(strict=)`, `zebra_agent/commons/__init__.py`) | One launch choke point for library workflows (goals, direct runs, routines, subworkflows); honest reversibility hints; strict gym mode (`always_reversible` only); `commons_exportable()` keeps protected workflows home | — |
| 1 | #228 S1 Zebra + device identity | Zebra key and device keys in the credential store, pairing with sphere and `observed`, local `DEVICE_CERT`/`DEVICE_REVOKE`, deployment owner, keys in the UI, Zebra key backup and restore | — |
| 1 | #229 S2a Provenance | `WorkflowLibrary.save()` as the one save path, canonical hash, `commons` block (incl. `sphere` / `tainted_by` / `share_with` / `foreign_users`) | S0 |
| 2 | #229 S2b Export + shared pieces | Signed single-workflow export/import, `c:` definition ids, `sharing` trust domain, `commons_pii_scan`, `save(writer="adopt")` | S1, S2a |
| 2 | #238 Private genealogy | Family tree per workflow on this deployment: versions, writers, diffs with reasons, leak-guard hits; sphere and share status once S3b-1 lands | S2a |
| 3 | #230 S3 Judged import | `commons_import.yaml`, gym import mode (strict), supervised pre-run approval at the choke point | S0, S2b |
| 3 | #236 S3b-1 Sync logic | `CommonsClient` ABC + in-memory client, spheres, suggest-and-approve, sensitivity and confidentiality scans, `observed_share_approval`, `SKILL` events, lineage merge and forks, `SYNC_DIRECTION` | S1, S2b, #237 |
| 4 | #246 S3b-2 Private relay | `nostr-sdk` client, private strfry Quadlet (NIP-42), publishing certs and revokes, receipts, encryption, offline queue. Human gate: keys, CI vars, proxy | S3b-1 |
| 5 | #231 S4 Commons relay + publish | Public strfry Quadlet, `commons_offer.yaml`, receipts, mirroring. Human gate: relay key | S3, S3b-2 |
| 5 | #232 S5 Attestations + subscribe (**code shipped, off by default**) | Subscription, `WorkflowOfferModel`, automatic attestations, `/commons/` page. Needs a second Zebra instance for its E2E test | S4 |
| 6 | #233 S6 Web of trust | Trust edges, human vouching, transitive local trust, import score (no market term) | S5 |
| 6 | #235 S8 Dream-cycle integration | Zebra proposes offers and imports; `sharing` promotion requests; no trades | S5, S6 |
| 6 | #247 Public genealogy | Commons lineage, adoptions, attestations, vouching tree, trust paths; no price history | S5, #238 |
| parked | #234 S7 Reputation market | Ledger replay, LMSR, `GRANT` / `TRADE` / `OUTCOME`, settlement, market UI, dream-cycle trades, price history. Its own later theme (`phase::19-reputation-market`); simulate first | S6 |

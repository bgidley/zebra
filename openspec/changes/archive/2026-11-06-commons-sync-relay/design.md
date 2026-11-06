## Context

S3b-1 (#236) gave `CommonsClient`, `SKILL` events (plaintext, `["enc","none"]`), `SyncService`
and the *Skill Share* / *Skill Receive* workflows over `InMemoryCommonsClient`. S1 (#228) keeps
`DEVICE_CERT` / `DEVICE_REVOKE` locally and rejects a revoked device's events outright. Design:
`specs/zebra-commons-design.md` (Identity, Event kinds, Skill sync S3b, Infrastructure).

## Goals / Non-Goals

**Goals:** a real relay client, NIP-42 auth with the device key, NIP-44 `SKILL`s, certs and
revokes on the relay, operator-signed receipts and receipt-order revocation, an offline queue,
off-by-default wiring, the relay's infrastructure files and a runbook.

**Non-goals:** installing or starting the relay (owner step), the public Commons relay and
mirroring (S4, #231), read restriction on the relay, more than one relay.

## Decisions

### nostr-sdk, behind two modules
`nostr-sdk` 0.45.1 (rust-nostr bindings, `cp39-abi3` wheels incl. manylinux aarch64) works on
this host's CPython 3.14. Only `zebra_agent/commons/nostr.py` imports it. Findings that shaped
the code:
- Its NIP-42 authenticator calls back into Python from a Rust thread and fails with "no running
  event loop" unless `uniffi_set_event_loop()` is set; the transport sets it to the running loop
  before every call.
- A client left open at interpreter exit can segfault; the transport always `shutdown()`s.
- A send to an unreachable relay returns `failed: {url: "timeout"}` rather than raising, and a
  fetch returns nothing; the transport checks `try_connect` first and raises `RelayUnavailable`.

The client logic (`RelayCommonsClient`, `Outbox`) is in `commons/relay.py` over a two-method
`RelayTransport` (`send`, `query`), so it is unit-tested with a fake transport and the raw
WebSocket fallback stays a one-class swap. Our own `Event` / `sign_event` (btclib BIP-340) stay
the event model; nostr-sdk only carries JSON.

### NIP-42 in strfry means NIP-70 protected events
strfry 1.1.3 (`docker.io/dockurr/strfry`) asks for AUTH only for NIP-70 protected events
(`["-"]` tag) and passes the authenticated key to the write-policy plugin only for them; this
build has no read restriction. So:
- `SKILL` events carry `["-"]`: strfry makes the publisher AUTH as the signing device, and the
  plugin accepts a `SKILL` only when `authed == pubkey` and that device holds a valid, unrevoked
  cert from a registered Zebra key.
- `DEVICE_CERT` / `DEVICE_REVOKE` (made in S1, unprotected, also meant for the public relay later)
  are accepted by **author**: a registered Zebra key. strfry verifies every signature, so only
  the Zebra key can author them; re-publishing someone's own signed cert is harmless.
- `RECEIPT`s are accepted only from the operator key. Everything else is rejected.
- Reads are open to anyone who can reach the relay: `SKILL` content is ciphertext, but who sends
  to whom, sizes and timing, and cert labels/spheres are visible (certs are public by design).

### Encryption
NIP-44 v2 via nostr-sdk, one ciphertext per recipient device (the S3b-1 per-device events). The
sender's device key and the recipient's device key derive the conversation key; the receiver
decrypts with its device secret and the event's signer. Plaintext over 65535 bytes cannot be
NIP-44 encrypted: building refuses it (`SkillRefused`). The relay config raises
`maxEventSize` to 128 KiB for the base64 overhead.

### Receipts: plugin journals, sidecar signs
The write-policy plugin (`deploy/podman/sync-relay/write_policy.py`, stdlib only: it runs on the
image's Python 3.11) sees every write sequentially, so it assigns `seq` in acceptance order and
appends `{seq, id, kind, pubkey, device}` to a journal on a shared volume (fsync) before
answering `accept`; duplicates are not journalled again. The sidecar
(`python -m zebra_agent.commons.receipts`, in the Zebra image, operator secret from
`ZEBRA_SYNC_OPERATOR_SECRET`) tails the journal, signs `RECEIPT` (kind 1246, tags `e`, `k`,
`seq`, content `{seq, event_id}`) and publishes it, resuming from a state file. Order is fixed
when the event is written, so a sidecar outage only delays receipts. The plugin also rebuilds its
allow-list (registered Zebra keys from `allowlist.json`, devices from journalled certs and
revokes) from the journal at start.

### Revocation by receipt order
`verify_device_chain(..., receipt_seq=, event_id=)`: with `receipt_seq` (event id → seq from
verified receipts) and an event id, a revoked device's event passes the revoke check only if it
has a receipt and every revoke of that device has a receipt with a higher `seq`; otherwise
`revoked` (or `no_receipt`). Without `receipt_seq` (no relay or no receipt key) the S1 rule
holds. Recipient selection (`devices()`, `skill_recipients`) never passes receipts: nothing is
sent to a revoked device.

### Offline queue
`Outbox` is a JSONL file (`<library>/.sync/outbox.jsonl`). `publish` appends when the relay is
unreachable or something is already queued (order is kept), then tries `flush()`; `flush` sends
in order, stops at the first unreachable send, and moves an event the relay permanently refuses
(`blocked:` / `invalid:` / `restricted:` / `pow:`) to `outbox.rejected.jsonl` with the reason.
A direct publish the relay refuses raises `PublishRefused`, so a `skill_send` to a relay that
does not know the device fails visibly. Sent events are recorded `sent` as before: a queued event
is sent, just later.

### Wiring
`zebra_agent_web/api/commons_sync.py` `build_sync_service()` returns None unless
`COMMONS_ENABLED`, `SYNC_RELAY` and an identity (Zebra pubkey, device key) are present. The daemon
tick (`sync_tick`) refreshes certs from the database, flushes, publishes identity and receives,
each step logged and never fatal. Settings: `SYNC_RELAY` (`ZEBRA_SYNC_RELAY`),
`SYNC_RECEIPT_PUBKEY` (`ZEBRA_SYNC_RECEIPT_PUBKEY`). The operator secret is only ever a secret
env var / CI variable for the sidecar.

## Risks / Trade-offs

- nostr-sdk is alpha (API moved between 0.3x and 0.45): pinned `<0.46`, isolated in `nostr.py`.
- Open reads leak metadata (above); a strfry with `restrictedReadKinds` could add
  `SKILL` later.
- The operator can reorder before journalling or drop events; receipts give a canonical order,
  not proof against the operator (design § Open questions).
- The plugin's journal grows ~200 bytes per event; retention deletes old `SKILL`s and their
  receipts from strfry, not journal lines (small; runbook notes it).

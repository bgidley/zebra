## Why

S3b-1 (#236) built skill sync between one Zebra's own devices (home, work) over an in-memory
transport, with `SKILL` content in plaintext and revocation by the S1 local rule (a revoked
device's events are rejected outright). For skills to really move between two deployments they
need a private relay, encryption to the recipient device, a relay outage that loses nothing, and
a revocation order a stolen device cannot backdate. This change (S3b-2, GitLab #246, epic #41)
ships that code **off by default**: with `ZEBRA_SYNC_RELAY` unset, prod behaves exactly as today,
and the relay infrastructure is in the repo but not installed by the deploy job.

## What Changes

- **Nostr transport** (`zebra_agent/commons/nostr.py`, the only importer of `nostr-sdk`, alpha):
  a `RelayTransport` over one relay with NIP-42 auth by the device key, plus NIP-44 v2
  encrypt/decrypt. `RelayCommonsClient` (`commons/relay.py`) implements `CommonsClient` over any
  `RelayTransport`: it re-verifies every fetched event, polls for `subscribe`, and queues
  publishes on disk while the relay is unreachable (`Outbox`, resent in order by `flush()`).
- **`SKILL` events are NIP-44 encrypted** to their one recipient device (tag `["enc","nip44"]`)
  and NIP-70 protected (`["-"]`), so strfry makes the publisher authenticate as the signing
  device. Receivers decrypt with their device key; plaintext (`enc none`) is rejected. A payload
  over the NIP-44 limit is refused before sending.
- **Receipts** (`commons/receipts.py`): `RECEIPT {seq, event_id}` (provisional kind 1246) signed
  by the relay operator key. The relay's write-policy plugin assigns `seq` in acceptance order and
  journals it; a small sidecar (`python -m zebra_agent.commons.receipts`) signs and publishes the
  receipts. Readers verify receipts against `ZEBRA_SYNC_RECEIPT_PUBKEY`.
- **Revocation by receipt order:** with receipts configured, a revoked device's event is accepted
  only if its receipt `seq` precedes the revoke's; no receipt, or a revoke without one, rejects it.
  With no relay configured the S1 local rule is unchanged. Choosing recipients still excludes any
  revoked device.
- **Certs and revokes on the relay:** `SyncService.publish_identity()` publishes the held
  `DEVICE_CERT` / `DEVICE_REVOKE` events; `refresh()` pulls this Zebra's certs, revokes and the
  receipts it needs, so a device learns its siblings from the relay.
- **Wiring:** the web app builds the `SyncService` with the relay client only when
  `COMMONS_ENABLED` and `ZEBRA_SYNC_RELAY` are set and this device has a Zebra identity; the
  daemon tick then flushes the outbox, publishes identity and receives pending skills. Unset:
  no `__commons_sync__`, no connection, no change.
- **Infrastructure files, not deployed:** `deploy/podman/sync-relay/` holds a strfry Quadlet,
  its config, the write-policy plugin (accepts only `SKILL`, `DEVICE_CERT`, `DEVICE_REVOKE` and
  operator `RECEIPT`s from registered Zebra keys and their certified, unrevoked devices), the
  receipt sidecar Quadlet and a 90-day retention timer. `scripts/deploy-podman.sh` installs only
  `deploy/podman/quadlet/*.container`, so none of it is picked up.
- **Runbook** `specs/commons-sync-relay-runbook.md`: the owner's steps to bring it up.

## Capabilities

### New Capabilities
- `commons-sync-relay`: the relay transport and offline queue, `SKILL` encryption, receipts and
  receipt-order revocation, identity publishing, off-by-default wiring and the relay policy.

### Modified Capabilities
- `commons-identity`: cert-chain verification orders revocation by relay receipts when a receipt
  key is configured.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With `ZEBRA_SYNC_RELAY` unset (or the Commons off) prod behaves exactly as before: no sync service in the engine, no relay connection, and the deploy job installs and starts no relay unit | Wiring unit tests (no `__commons_sync__` unless both are set and an identity exists; the daemon tick does nothing without it); a test that the deploy script installs only `deploy/podman/quadlet/*.container` and no relay file is there; prod logs show no sync activity after deploy |
| O2 | Over a real strfry relay, a workflow approved at work appears at home: each `SKILL` is NIP-44 ciphertext addressed to one certified device of the `share_with` spheres, only that device can decrypt it, and the relay refuses unknown authors, unprotected `SKILL`s and other kinds | Integration test against a throwaway strfry container (skips with a reason when podman or the image is missing); unit tests of NIP-44 recipients and the write-policy plugin |
| O3 | A relay outage loses nothing: a share approved while the relay is down is queued on disk and arrives once the relay is back | Outbox unit tests (queue, ordered resend, survives a restart, permanent refusal raises); integration test stops the relay, approves a share, starts it and receives it |
| O4 | With a receipt key configured, a revoked device's event is accepted only if its operator-signed receipt precedes the revoke's; no receipt, a forged receipt or a revoke without a receipt rejects it; without a relay the S1 rule still holds | Receipt and `verify_device_chain` unit tests; the integration test checks the sidecar signs a receipt for every stored event |
| O5 | The owner can bring the relay up from the runbook alone, with root-only steps marked | `specs/commons-sync-relay-runbook.md` (operator key, CI variables, Quadlets, reverse proxy, allow-list, pairing, manual E2E), summary posted on #246 |

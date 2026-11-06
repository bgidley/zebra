> Branch: `f246/commons-sync-relay`. Reference `Refs #246` in commits (do not close #246: the
> manual two-deployment E2E closes it).

## 1. Transport

- [x] 1.1 `nostr-sdk` dependency; `commons/nostr.py`: `NostrSdkTransport` (NIP-42 by device key, event-loop fix, shutdown), `nip44_encrypt` / `nip44_decrypt`
- [x] 1.2 `commons/relay.py`: `RelayTransport`, `RelayUnavailable`, `Outbox`, `RelayCommonsClient` (verify on fetch, polling subscribe, queue + ordered flush, permanent refusal)
- [x] 1.3 `Filter`: `events` (`#e`), `limit`, `to_nostr()`
- [x] 1.4 Unit tests with a fake transport

## 2. Encryption, receipts, revocation

- [x] 2.1 `skill.py`: NIP-44 per recipient, `["-"]`, `["enc","nip44"]`; verify decrypts, rejects plaintext; size limit
- [x] 2.2 `commons/receipts.py`: `RECEIPT_KIND`, `make_receipt`, `receipt_order`, `ReceiptSigner` + CLI
- [x] 2.3 `identity.verify_device_chain` / `verify_attributed`: receipt order when receipts are given
- [x] 2.4 `SyncService`: `receipt_pubkey`, `refresh()` (certs, revokes, receipts), `publish_identity()`, `flush()`; send publishes identity first
- [x] 2.5 Unit tests: NIP-44 recipients, receipts, revocation by receipt order

## 3. Wiring (off by default)

- [x] 3.1 Settings `SYNC_RELAY`, `SYNC_RECEIPT_PUBKEY`; `api/commons_sync.py` `build_sync_service`, `sync_tick`
- [x] 3.2 `agent_engine` injects only when built; daemon tick calls `sync_tick` only with a service
- [x] 3.3 Tests: unset → nothing; set → service built

## 4. Infrastructure (not deployed)

- [x] 4.1 `deploy/podman/sync-relay/`: strfry Quadlet, `strfry.conf`, `write_policy.py`, `allowlist.json.example`, receipt sidecar Quadlet, retention service + timer
- [x] 4.2 Plugin unit tests; test that the deploy job does not install them

## 5. Integration, docs

- [x] 5.1 Integration test over a throwaway strfry container (skips without podman/image): home + observed work E2E, outage + resend, receipts
- [x] 5.2 `specs/commons-sync-relay-runbook.md` (+ `specs/AGENTS.md`), `specs/zebra-commons-design.md`, `specs/zebra-as-is.md`, `zebra-agent/AGENTS.md`, CLAUDE.md settings table
- [x] 5.3 Post outcomes and runbook summary on #246

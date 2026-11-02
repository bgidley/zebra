## Why

The Zebra Commons (#41) needs an identity before anything can be offered, attested or synced.
Each Zebra is one identity (the **Zebra key**) running on one or more deployments ("devices", e.g.
home and work), each with its own **device key** certified by the Zebra key. Reputation belongs to
the Zebra, devices come and go, and Commons acts for exactly one owner per deployment (owner
decision a). This is slice S1 of [specs/zebra-commons-design.md](../../../specs/zebra-commons-design.md).
Refs #228. Requirement REQ-NET-001.

## What Changes

- New `zebra_agent/commons/` package (no Django, no network):
  - `keys.py`: secp256k1 key generation, BIP-340 Schnorr sign/verify, `npub`/`nsec` (NIP-19
    bech32). Backed by `btclib-secp256k1` (libsecp256k1 bindings), see design.
  - `events.py`: NIP-01 events (id = sha256 of the canonical array, Schnorr signature).
  - `identity.py`: `DEVICE_CERT` / `DEVICE_REVOKE` builders, the pairing code and fingerprint,
    and the cert-chain verify helper (device key → valid, unexpired, unrevoked cert → Zebra key).
    A revoked device's signatures are rejected outright until relay receipts exist (#246).
  - `keystore.py`: `CommonsKeys` keeps the Zebra key (`integration_name="commons-zebra"`) and the
    device key (`commons-device`) in a `CredentialStore`, with nsec backup and restore.
- Web (`zebra-agent-web`):
  - `SystemStateModel` gains `zebra_pubkey`, `zebra_display_name`, `device_pubkey`,
    `device_label`, `sphere`, `sphere_observed`, `sync_direction`, `commons_owner_user_id`
    (default: the first user). New `CommonsDeviceModel` keeps the signed certs and revokes.
  - `/commons/` page: the Zebra npub, the owner, this device and the device list (label, sphere,
    observed, status). Owner-only actions: start a new Zebra, pair a device (asks "who manages
    this device?"), import a cert on the new device, revoke, back up and restore the Zebra key.
  - `COMMONS_ENABLED` (`ZEBRA_COMMONS_ENABLED`, default off) and `COMMONS_KEY_DIR`
    (`ZEBRA_COMMONS_KEY_DIR`). With Commons off no key is made and the actions are refused.
- Nothing is published: certs and revokes are created and verified locally (publishing is #246).

## Capabilities

### New Capabilities
- `commons-identity`: Zebra key, certified device keys with spheres, revocation, deployment owner,
  key backup/restore and the Commons identity page.

### Modified Capabilities
<!-- None. -->

## Non-goals

- Publishing certs or revokes, relays, receipts, `nostr-sdk` (#246).
- Receipt-ordered acceptance of a revoked device's earlier events (#246).
- Provenance, offers, sync, the `sharing` trust domain (S2+).
- QR codes: the pairing code is the device npub plus a short fingerprint to compare by eye.
- Passphrase-encrypted backup (NIP-49); the backup is the standard `nsec`.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With Commons on, a deployment gets one Zebra identity whose secret keys live only in the credential store, and the page shows its npub, the owner and this device | Unit tests: BIP-340 test vectors pass; keys are created once under `commons-zebra` / `commons-device`; the DB holds only public keys; a page test after "Start a new Zebra" shows the npub, owner and one device |
| O2 | A second device can be paired into the same Zebra with a label, a sphere and the observed flag, and its cert verifies on both deployments | Tests: device B's pairing code → owner on A pairs it as `work`, managed by someone else → `verify_device_chain` accepts with sphere `work`, observed true; B imports the cert and shows A's npub; tampered, expired, foreign-key certs and a cert replayed onto another device are rejected (a cert is only useful to the holder of its device secret) |
| O3 | Revoking a device makes its signatures fail verification outright on the revoking deployment (propagation to other deployments is #246) while the Zebra npub and other devices are unchanged | Tests: after revoke, an event signed by the revoked device key is rejected with reason `revoked`, the device shows as revoked, the npub is the same and the local device still verifies; a revoked key cannot be re-paired |
| O4 | Only the owner manages the identity, and the owner can back up and restore the Zebra key (holding the `nsec` *is* the identity, so it is shown only to the owner on an explicit request and never logged) | Tests: the owner defaults to the first user; a non-owner gets 403 on every action and never sees the `nsec`; the backup response is `no-store` and the key is absent from logs; nsec restored on a fresh deployment gives the same npub and re-certifies the device; an invalid nsec is rejected and changes nothing |
| O5 | Off by default and harmless on prod; keys survive restarts and switching off | Tests: with `COMMONS_ENABLED` off no key is created, the page says so and actions 404; switching off after use keeps the keys and switching back on shows the same npub; keys reload from the file store in a new process; migration applies; the master deploy and smoke stages are green |

## Impact

- New dependency `btclib-secp256k1` (zebra-agent). New modules under `zebra_agent/commons/`.
- Migration adding `SystemStateModel` fields and `zebra_commons_devices`.
- New web module `zebra_agent_web/api/commons_views.py`, template `pages/commons.html`, nav link
  (shown only when Commons is on). Quadlet: a `zebra-commons-keys` volume for the key directory.
- Docs: `specs/zebra-commons-design.md` (S1 shipped), `specs/zebra-as-is.md`, `zebra-agent/AGENTS.md`,
  `zebra-agent-web/AGENTS.md`, `CLAUDE.md` settings table.

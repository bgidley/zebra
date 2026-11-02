> Branch: `f228/commons-identity`. Reference `#228` in commits (`Refs #228`).

## 1. Core (zebra-agent)

- [x] 1.1 Add `btclib-secp256k1`; `commons/keys.py` (generate, pubkey, BIP-340 sign/verify, npub/nsec)
- [x] 1.2 `commons/events.py`: NIP-01 `Event`, id, sign, verify, JSON round trip
- [x] 1.3 `commons/identity.py`: cert/revoke builders, pairing code + fingerprint, cert code, `verify_device_chain`, `verify_attributed`
- [x] 1.4 `commons/keystore.py`: `CommonsKeys` over `CredentialStore` (device key, Zebra key, backup, restore)

## 2. Web (zebra-agent-web)

- [x] 2.1 `SystemStateModel` fields, `CommonsDeviceModel`, migration
- [x] 2.2 Settings `COMMONS_ENABLED`, `COMMONS_KEY_DIR`; quadlet volume
- [x] 2.3 `api/commons_identity.py` service (owner, start, pair, import, revoke, backup, restore)
- [x] 2.4 `api/commons_views.py` + `pages/commons.html` + URLs + nav link (when enabled)

## 3. Tests

- [x] 3.1 Keys: BIP-340 vectors, bech32 round trip and invalid input
- [x] 3.2 Events and verify helper: valid, tampered, foreign key, expired, revoked, re-cert newest wins
- [x] 3.3 Keystore: created once, backup/restore, invalid nsec
- [x] 3.4 Web: off by default, start, pair B as work/observed, import on B, revoke, non-owner 403, backup/restore
- [x] 3.5 Web import rejections (review fix): a cert replayed onto another device, changed content or sig, signed by a non-Zebra key, expired, or from a second Zebra; each leaves state unchanged

## 4. Docs & delivery

- [x] 4.1 `specs/zebra-commons-design.md`, `specs/zebra-as-is.md`, `zebra-agent/AGENTS.md`, `zebra-agent-web/AGENTS.md`, `CLAUDE.md` settings
- [x] 4.2 ruff check + format; full unit suites green
- [x] 4.3 Push branch, GitLab pipeline green

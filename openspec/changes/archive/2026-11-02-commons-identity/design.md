## Context

S1 of the Zebra Commons ([specs/zebra-commons-design.md](../../../specs/zebra-commons-design.md),
"Identity (S1)"). Nothing is published yet, so everything here is local: keys, certs, revokes and
their verification. The events are real NIP-01 Nostr events so #246 can publish them unchanged.

## Goals / Non-Goals

**Goals:** one Zebra key per Zebra; one device key per deployment; human-confirmed pairing with
sphere + `observed`; local `DEVICE_CERT` / `DEVICE_REVOKE`; a pure verify helper; one owner per
deployment; key backup/restore; a page showing it all; a master switch, off by default.

**Non-goals:** relays, receipts, `nostr-sdk`, QR codes, encrypted (NIP-49) backups, sync.

## Decisions

### D1. Crypto library: `btclib-secp256k1`
We need secp256k1 keys and BIP-340 Schnorr signatures (Nostr). Candidates checked 2026-10-30:

| Library | Verdict |
|---|---|
| `coincurve` 21.0 | The usual choice, but no CPython 3.14 wheels (we run 3.14), and its sdist fails to build here (`Expected exactly one LICENSE file in cffi distribution`). The slim image has no compiler either. |
| `secp256k1` (rustyrussell) 0.14 | No `linux/aarch64` wheels (prod is aarch64), no 3.14. |
| `btclib` / `ecc` | Pure Python (not constant time), very young `ecc` dependency, releases almost daily. |
| `nostr-sdk` | Has wheels, but it is alpha and deliberately left to #246. |
| **`btclib-secp256k1` 0.8** | **Chosen.** CFFI bindings to bitcoin-core's libsecp256k1 (the reference, constant-time implementation), bundled in wheels for CPython 3.11–3.15 on linux x86_64/aarch64 (glibc and musl), macOS and Windows. Maintained (release 2026-10-23), MIT, typed. `ssa.sign` runs BIP-340's verify-after-sign. |

It passes the BIP-340 test vectors (unit test). Only `zebra_agent/commons/keys.py` imports it, so
swapping it (e.g. for `coincurve` once it ships 3.14 wheels, or `nostr-sdk` in #246) touches one
file. NIP-19 bech32 (`npub`/`nsec`) is the 40-line BIP-173 reference code inlined in `keys.py`:
the `bech32` package is unmaintained and the code is tiny and pinned by tests.

### D2. Keys live in a `CredentialStore`, public keys in the DB
`CommonsKeys(store, namespace="instance")` reads and writes the hex secret under
`(namespace, "commons-zebra" | "commons-device", "secret_key")`. Commons is per deployment, not
per user, so the namespace is a fixed instance name rather than a user id (an owner change must not
lose the keys). The web app uses a `FileCredentialStore` rooted at `COMMONS_KEY_DIR`
(default `~/.zebra-agent/commons-keys`, 0600 files): the OS keyring is unusable in the headless
prod container. Prod mounts a named volume (`zebra-commons-keys`) there so keys survive redeploys.
`SystemStateModel` holds only public keys and labels.

### D3. Events
NIP-01: `id = sha256(json([0, pubkey, created_at, kind, tags, content]))` with compact separators
and `ensure_ascii=False`; `sig` = BIP-340 over the id. Kinds are provisional constants until S4
fixes the numbers: `DEVICE_CERT_KIND = 30228` (addressable, `d` = device pubkey),
`DEVICE_REVOKE_KIND = 1228` (regular). Both carry `["p", device]`, `["t","zebra-commons"]`,
`["v","1"]`. Cert content: `{label, sphere, observed, expires_at?}` (unix seconds). Revoke content:
`{reason}`.

### D4. Verify helper (pure, no DB)
`verify_device_chain(device_pubkey, zebra_pubkey, events, now)`:
1. Drop events with a bad id or signature, or not signed by `zebra_pubkey`.
2. Any `DEVICE_REVOKE` naming the device → rejected `revoked` (no receipts yet, so outright).
3. Latest `DEVICE_CERT` with `d` and `p` = the device (addressable: newest `created_at` wins).
   None → `no_cert`; malformed content → `bad_cert`; `expires_at <= now` → `expired`.
4. Else ok, with the parsed cert.

`verify_attributed(event, zebra_pubkey, events, now)` checks the event's own signature, accepts the
Zebra key itself, and otherwise runs the chain for `event.pubkey`.

### D5. Pairing without a network
1. New device B: the page shows its **pairing code** (its device `npub`) and a fingerprint
   (`XXXX-XXXX`, base32 of sha256(pubkey)) to compare by eye.
2. On A (holds the Zebra key) the owner enters the code, a label, "who manages this device?"
   (me / someone else → `observed`) and a sphere (`home`, `work` or a name), optionally an expiry.
   A shows the same fingerprint, signs the cert, stores it, and shows a **cert code**
   (`zcert1` + base64url of the event JSON).
3. On B the owner pastes the cert code. B verifies it (signature, names B's key, not expired)
   and adopts the Zebra pubkey, label, sphere and observed from it.

Re-pairing a non-revoked key re-issues its cert (this is how a sphere changes: it needs the Zebra
key). A revoked key cannot be re-paired; a lost device pairs again with a fresh key. The local
device cannot be revoked from its own page.

### D6. Start, backup, restore
- **Start a new Zebra** (owner, Commons on, no identity yet): generates the Zebra key and
  self-certifies this device (label, manager, sphere from the form).
- **Back up**: a POST reveals the `nsec` once on the page (no-store response). Standard NIP-19, so
  any Nostr tool can hold it.
- **Restore**: paste an `nsec`. The Zebra key is replaced, `zebra_pubkey` set, and this device is
  re-certified under it. Devices certified by a previous key are no longer listed (rows are keyed by
  Zebra pubkey). Losing the key without a backup means a new identity: there is no recovery path
  and so no takeover path.

### D7. Owner
`commons_owner_user_id` defaults to the first user (lowest id) the first time it is read, and is
persisted. Every Commons action checks `request.user.id == owner`; others get 403 and a read-only
page.

### D8. Master switch
`COMMONS_ENABLED` (`ZEBRA_COMMONS_ENABLED`, default off). Off: the page explains it is off, no key
is created, every action returns 404, and the nav link is hidden.

## Risks / Trade-offs

- `nsec` shown in a browser: owner-only, POST-only, `Cache-Control: no-store`. NIP-49 encrypted
  export is a possible later improvement.
- Key file loss in the container without the volume: mitigated by the quadlet volume and backup.
- Kind numbers are provisional until S4; nothing is published yet so changing them is free.
- `btclib-secp256k1` is a smaller project than `coincurve`; isolated behind `keys.py` (D1).

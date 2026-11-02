## ADDED Requirements

### Requirement: Zebra and device keys
With Commons enabled, a deployment SHALL keep its Zebra secret key under `integration_name="commons-zebra"` and its device secret key under `integration_name="commons-device"` in a `CredentialStore`, and SHALL store only the public keys in the database. Signatures SHALL be BIP-340 Schnorr over secp256k1, and public keys SHALL be shown as NIP-19 `npub`.

#### Scenario: Start a new Zebra
- **WHEN** the owner starts a new Zebra on a deployment with no identity
- **THEN** a Zebra key and a device key are created in the credential store, `SystemStateModel.zebra_pubkey` and `device_pubkey` hold the public keys, and this device has a `DEVICE_CERT` signed by the Zebra key

#### Scenario: Keys are created once
- **WHEN** the device key is requested twice
- **THEN** the same key is returned both times

### Requirement: Device certificates and pairing
A `DEVICE_CERT` SHALL be a NIP-01 event signed by the Zebra key, with tags `d` and `p` set to the device public key, and content `{label, sphere, observed, expires_at?}`. Pairing SHALL take the new device's pairing code (its npub), a label, a sphere and the answer to "who manages this device?" (someone else means `observed`), and SHALL produce a cert code the new device imports after verifying it names its own key.

#### Scenario: Pair a managed work device
- **WHEN** the owner pairs device B's code as label "work laptop", sphere `work`, managed by someone else
- **THEN** the cert chain for B verifies with sphere `work` and `observed` true, and B is listed with its sphere

#### Scenario: Import on the new device
- **WHEN** device B imports the cert code produced for it
- **THEN** B records the Zebra public key, label, sphere and observed flag from the cert

#### Scenario: Cert for another device
- **WHEN** a device imports a cert code whose `p` tag names a different device key
- **THEN** the import is rejected and nothing changes

#### Scenario: Bad cert on import
- **WHEN** a device imports a decodable cert code whose content or signature was altered, that is signed by a key other than the one it names, that has expired, or that comes from a different Zebra than the one the device already belongs to
- **THEN** the import is rejected and nothing changes

### Requirement: Cert-chain verification
The verify helper SHALL accept an event when it is signed by the Zebra key, or when its signer has a validly signed, unexpired `DEVICE_CERT` from the Zebra key and no `DEVICE_REVOKE` from the Zebra key. Until relay receipts exist, a revoked device's events SHALL be rejected outright.

#### Scenario: Tampered or foreign cert
- **WHEN** a cert's content has been altered after signing, or it is signed by a key other than the Zebra key
- **THEN** verification fails with reason `no_cert`

#### Scenario: Expired cert
- **WHEN** a cert's `expires_at` is in the past
- **THEN** verification fails with reason `expired`

#### Scenario: Revoked device
- **WHEN** the owner revokes device B
- **THEN** events signed by B fail verification with reason `revoked`, the Zebra npub is unchanged, other devices still verify, and B's key cannot be paired again

### Requirement: Deployment owner
Each deployment SHALL have one Commons owner, `commons_owner_user_id`, defaulting to its first user. Only the owner SHALL start, pair, import, revoke, back up or restore.

#### Scenario: Non-owner action
- **WHEN** a signed-in user who is not the owner posts any Commons action
- **THEN** the response is 403 and nothing changes

### Requirement: Zebra key backup and restore
The owner SHALL be able to reveal the Zebra key as an `nsec` and to restore a Zebra key from an `nsec`. Restoring SHALL set the Zebra public key and re-certify this device under it.

#### Scenario: Restore on a fresh deployment
- **WHEN** the backup `nsec` of Zebra Z is restored on a fresh deployment
- **THEN** the deployment shows Z's npub and its own device verifies under Z

#### Scenario: Invalid backup
- **WHEN** the pasted text is not a valid `nsec`
- **THEN** the restore is rejected and the identity is unchanged

### Requirement: Commons master switch
`COMMONS_ENABLED` (env `ZEBRA_COMMONS_ENABLED`) SHALL default to off. While off, no Commons key SHALL be created, the Commons page SHALL say Commons is off, and every Commons action SHALL return 404.

#### Scenario: Off by default
- **WHEN** Commons is off and the owner opens the Commons page and posts "start"
- **THEN** the page says Commons is off, the post returns 404, and the credential store holds no Commons key

## MODIFIED Requirements

### Requirement: Zebra and device keys
With Commons enabled, a deployment SHALL keep its Zebra secret key under `integration_name="commons-zebra"` and its device secret key under `integration_name="commons-device"` in a `CredentialStore`, and SHALL store only the public keys in the database. Signatures SHALL be BIP-340 Schnorr over secp256k1, and public keys SHALL be shown as NIP-19 `npub`. Keys in a file credential store SHALL survive a process restart.

#### Scenario: Start a new Zebra
- **WHEN** the owner starts a new Zebra on a deployment with no identity
- **THEN** a Zebra key and a device key are created in the credential store, `SystemStateModel.zebra_pubkey` and `device_pubkey` hold the public keys, and this device has a `DEVICE_CERT` signed by the Zebra key

#### Scenario: Keys are created once
- **WHEN** the device key is requested twice
- **THEN** the same key is returned both times

#### Scenario: Keys survive a real restart
- **WHEN** one Python process creates the identity in a key directory and a fresh process reads that directory
- **THEN** the fresh process has the same npub and device public key, and the device's `DEVICE_CERT` from the first process verifies against them

### Requirement: Commons master switch
`COMMONS_ENABLED` (env `ZEBRA_COMMONS_ENABLED`) SHALL default to off. While off, no Commons key SHALL be created, the Commons page SHALL say Commons is off, and every Commons action SHALL return 404.

#### Scenario: Off by default
- **WHEN** Commons is off and the owner opens the Commons page and posts "start"
- **THEN** the page says Commons is off, the post returns 404, and the credential store holds no Commons key

#### Scenario: Every action is off
- **WHEN** Commons is off and the owner posts start, pair, import, revoke, backup or restore
- **THEN** each returns 404 and no key directory is created

#### Scenario: Turned off over existing keys
- **WHEN** a deployment that has keys turns Commons off and the owner posts any of the six actions
- **THEN** each returns 404 and the stored keys are unchanged

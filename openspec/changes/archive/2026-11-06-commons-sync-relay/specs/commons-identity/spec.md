## MODIFIED Requirements

### Requirement: Cert-chain verification
The verify helper SHALL accept an event when it is signed by the Zebra key, or when its signer has a validly signed, unexpired `DEVICE_CERT` from the Zebra key and no `DEVICE_REVOKE` from the Zebra key. When verified relay receipts are supplied, an event from a revoked device SHALL be accepted only if its receipt `seq` precedes the receipt `seq` of every revoke of that device; an event with no receipt, or a revoke with no receipt, SHALL reject it. Without receipts (no relay configured), a revoked device's events SHALL be rejected outright.

#### Scenario: Tampered or foreign cert
- **WHEN** a cert's content has been altered after signing, or it is signed by a key other than the Zebra key
- **THEN** verification fails with reason `no_cert`

#### Scenario: Expired cert
- **WHEN** a cert's `expires_at` is in the past
- **THEN** verification fails with reason `expired`

#### Scenario: Revoked device
- **WHEN** the owner revokes device B and no receipts are supplied
- **THEN** events signed by B fail verification with reason `revoked`, the Zebra npub is unchanged, other devices still verify, and B's key cannot be paired again

#### Scenario: Event stored before the revoke
- **WHEN** B's event has receipt `seq` 5 and B's revoke has receipt `seq` 9
- **THEN** B's event verifies, while an event of B with `seq` 12 or with no receipt fails

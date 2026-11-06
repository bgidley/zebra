## ADDED Requirements

### Requirement: Relay client
Skill sync SHALL reach the private relay only through a `CommonsClient` implementation that
re-verifies every fetched event's id and signature and keeps the hard filter. `nostr-sdk` SHALL be
imported only inside `zebra_agent/commons/`.

#### Scenario: Forged event from the relay
- **WHEN** the relay returns an event whose signature does not verify
- **THEN** the client drops it and returns only valid events

### Requirement: Encrypted SKILL events
Each `SKILL` event SHALL carry its content as NIP-44 ciphertext to its one recipient device and be
NIP-70 protected. A receiver SHALL decrypt it with its own device key and SHALL reject a `SKILL`
that is not NIP-44 encrypted or does not decrypt.

#### Scenario: Only the addressed device can read a copy
- **WHEN** a workflow shared with `home` is sent and a work device holds the home copy
- **THEN** the work device cannot decrypt it and verification fails

#### Scenario: Plaintext SKILL
- **WHEN** a `SKILL` with `["enc","none"]` arrives
- **THEN** verification fails with `not_encrypted`

### Requirement: Offline queue
Publishing SHALL NOT lose an event while the relay is unreachable: the event SHALL be queued on
disk and resent in order once the relay is reachable, and a permanent refusal by the relay SHALL be
reported rather than retried forever.

#### Scenario: Relay outage
- **WHEN** a share is sent while the relay is down and the relay comes back
- **THEN** the next flush delivers the queued event and the receiver gets it

#### Scenario: Relay refuses the event
- **WHEN** the relay answers `blocked:` to a direct publish
- **THEN** publishing raises `PublishRefused` and nothing is queued

### Requirement: Receipts
Receipts SHALL be `RECEIPT {seq, event_id}` events signed by the relay operator key, with `seq`
assigned in the order the relay accepted events. A reader SHALL use only receipts whose signature
verifies against the configured `SYNC_RECEIPT_PUBKEY` and whose content matches its tags.

#### Scenario: Forged receipt
- **WHEN** a receipt is signed by any key other than the configured operator key
- **THEN** it is ignored

### Requirement: Identity on the relay
A device SHALL publish its Zebra's held `DEVICE_CERT` and `DEVICE_REVOKE` events to the private
relay before sending, and SHALL pull its own Zebra's certs and revokes from it, so devices learn
their siblings from the relay.

#### Scenario: Second device learns the first
- **WHEN** home has published its cert and work refreshes from the relay
- **THEN** work can address a share to the home device

### Requirement: Off by default
The sync service SHALL be built and injected only when the Commons is enabled, `ZEBRA_SYNC_RELAY`
is set and the device has a Zebra identity; otherwise no sync service, connection or background
sync step SHALL exist. The deploy job SHALL NOT install or start the relay units.

#### Scenario: Relay unset
- **WHEN** `ZEBRA_SYNC_RELAY` is unset
- **THEN** the engine has no `__commons_sync__` and the daemon tick does no sync work

### Requirement: Relay write policy
The private relay SHALL accept only `SKILL`, `DEVICE_CERT`, `DEVICE_REVOKE` and the operator's
`RECEIPT` events: certs and revokes authored by a registered Zebra key, `SKILL`s protected,
authenticated as and authored by a device with a valid, unexpired, unrevoked cert from one. Stored
`SKILL`s and their receipts SHALL be deleted after 90 days.

#### Scenario: Unregistered author
- **WHEN** a `SKILL` arrives from a device no registered Zebra key certified
- **THEN** the relay rejects it and journals no receipt

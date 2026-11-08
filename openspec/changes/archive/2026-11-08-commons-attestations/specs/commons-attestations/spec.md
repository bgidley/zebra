## ADDED Requirements

### Requirement: Off by default
The Zebra SHALL NOT subscribe to, fetch from or publish to a public relay, and SHALL NOT publish
attestations, unless the Commons is enabled, `ZEBRA_COMMONS_RELAYS` is set and the device has a
Zebra identity and device key.

#### Scenario: Relays unset
- **WHEN** `ZEBRA_COMMONS_RELAYS` is unset
- **THEN** the engine has no `__commons_exchange__`, a daemon tick fetches nothing, and `/commons/`
  shows empty offer sections saying publishing is off

### Requirement: Offer intake
Each poll SHALL fetch `OFFER` events with their publishers' certs, revokes and receipts, and store
an offer only when its signature, device attribution and content hash verify. One row SHALL exist
per content hash, owned by the instance owner, with status `seen`. Offers SHALL never be imported
automatically.

#### Scenario: Valid offer
- **WHEN** another Zebra's verified `OFFER` is fetched
- **THEN** it is mirrored and recorded as `seen` with name, summary, stats and publisher key

#### Scenario: Bad signature, wrong cert or tampered YAML
- **WHEN** an `OFFER` has a bad signature, is signed by a device without a cert from its `zebra`
  key, or its YAML does not hash to its `d` tag
- **THEN** nothing is stored

#### Scenario: Duplicate hash
- **WHEN** a second `OFFER` with an already stored content hash arrives
- **THEN** no second row is created and the existing row is unchanged

#### Scenario: Revoked device delists only its own offer
- **WHEN** the stored row's own `OFFER` event no longer verifies because its device was revoked
- **THEN** the `seen` row is delisted
- **WHEN** another Zebra offers a copy with the same hash signed by a device it revoked itself
- **THEN** the stored row stays `seen` (only the row's own event can delist it)

### Requirement: Offer status transitions
Offer status SHALL change only along `seen → judging | delisted`, `judging → adopted | rejected |
seen | delisted`, `rejected → judging | delisted`, `adopted → delisted`.

#### Scenario: Illegal transition
- **WHEN** an `adopted` offer is set to `seen`
- **THEN** the store raises and the status is unchanged

### Requirement: Import from an offer
The owner SHALL be able to start the judged *Commons Import* on a `seen` or `rejected` offer. The
import SHALL accept the `OFFER` and its certs as input, re-verify signature, attribution and hash
in the judge and again before adopting, and otherwise run the same gates as a file import.

#### Scenario: Tampered offer input
- **WHEN** the offer input's YAML is changed after signing
- **THEN** the judge rejects it and nothing is adopted

### Requirement: ATTEST events
An `ATTEST` SHALL be kind 1232 signed by a certified device key, tagged `L`=`zebra-commons`,
`l`=one of `adopted`, `rejected-ethics`, `rejected-gym`, `rejected-pii`, `pii-found`, `worked`,
`failed`, `x`=content hash, `zebra`=attesting Zebra, `t`, `v`, with content `{reason, rating?}`
where `reason` is from a fixed vocabulary for the label and `rating` an integer 1–5. Verification
SHALL refuse any other tag, key, label or reason.

#### Scenario: Round trip
- **WHEN** a device builds an `ATTEST` and a reader holds its cert
- **THEN** it verifies as coming from that Zebra with its label and hash

#### Scenario: Free text refused
- **WHEN** an attestation is built or received with a reason outside the vocabulary
- **THEN** building raises and verification fails

### Requirement: Automatic attestations
The Zebra SHALL publish an `ATTEST` for each judged import of a public offer that is adopted or
rejected by the personal-data scan, ethics or the gym, and `worked` / `failed` after each run of an
adopted workflow, only while the hash of its current YAML equals the offered hash. Imports of
export files SHALL never be attested.

#### Scenario: Adopted then worked
- **WHEN** B adopts A's offer and later runs it successfully
- **THEN** B publishes `adopted` then `worked` for that hash, and both appear on A's `/commons/`

#### Scenario: Modified copy
- **WHEN** the adopted workflow was changed locally and then runs
- **THEN** no attestation is published

### Requirement: No personal data in attestations
Attestation content and tags SHALL never contain goal text, outputs, workflow or person names, or
LLM-written text.

#### Scenario: Personal data in the run
- **WHEN** a goal and its output contain a name and an email address
- **THEN** no published `ATTEST` contains them in content or tags

### Requirement: Commons offers page
`/commons/` SHALL show this Zebra's npub, offers seen (status, publisher npub and fingerprint,
stats, worked / failed / rejected counts, Zebra's reason in its own voice), this Zebra's own offers
with attestations from other Zebras, and an owner-only "Import this" action, with empty states
when publishing is off.

#### Scenario: Not the owner
- **WHEN** a signed-in user who is not the owner posts "Import this"
- **THEN** the response is 403 and no import starts

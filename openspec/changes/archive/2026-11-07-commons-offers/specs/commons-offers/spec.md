## ADDED Requirements

### Requirement: Fixed event kinds
Commons event kinds SHALL be fixed in one table: `DEVICE_CERT` 30228, `DEVICE_REVOKE` 1228,
workflow export 31229, `SKILL` 4236, `RECEIPT` 1246, `OFFER` 30231, `ATTEST` 1232, `TRUST` 30233,
`GRANT` 1234, `TRADE` 1235, `OUTCOME` 1236. The public kinds SHALL be `OFFER`, `ATTEST`, `TRUST`,
`GRANT`, `TRADE`, `OUTCOME`, `RECEIPT`, `DEVICE_CERT` and `DEVICE_REVOKE`.

#### Scenario: Relay policies agree with the table
- **WHEN** the public and private relay write policies are loaded
- **THEN** their kind numbers equal the table's

### Requirement: Public hard filter
A client for a public relay SHALL refuse to publish an event whose kind is not public or that is
not tagged `["t","zebra-commons"]`, and every client SHALL refuse `SKILL` unless it is the private
relay.

#### Scenario: SKILL to a public relay
- **WHEN** a `SKILL` event is published to a public relay
- **THEN** publishing raises `PublishRefused` and the relay stores nothing

#### Scenario: Unlisted kind to a public relay
- **WHEN** an event of the workflow export kind is published to a public relay
- **THEN** publishing raises `PublishRefused`

### Requirement: OFFER event
An `OFFER` SHALL be an addressable event signed by a certified device key with content `{name,
summary, use_when, stats {runs, success_rate, avg_rating, gym_score}, actions, golden_tasks, yaml}`
(1–3 golden tasks), tags `d` and `x` equal to the content hash of `yaml`, `zebra` (publisher Zebra
pubkey), `t`=`zebra-commons` and `v`=`1`. Verification SHALL check the shape, that the hash of
`yaml` equals `d` and `x`, and that the signer is attributed to the `zebra` key by a valid cert.

#### Scenario: Offer round trip
- **WHEN** a device of Zebra Z builds an offer and a reader holds Z's cert for that device
- **THEN** the offer verifies as coming from Z with the workflow's content hash

#### Scenario: Tampered offer
- **WHEN** the offer's YAML is changed after signing, or the cert is missing
- **THEN** verification fails

### Requirement: Parent privacy
An `OFFER` SHALL carry a `parent` tag only when the workflow's `parent_sha256` was itself publicly
offered by this Zebra; otherwise it SHALL reference no ancestor at all.

#### Scenario: Private parent
- **WHEN** the parent version was never offered
- **THEN** the offer has no `parent` tag and no ancestor hash appears anywhere in it

#### Scenario: Public parent
- **WHEN** the parent version has an `OFFER` in the local mirror
- **THEN** the offer's `parent` tag is that hash

### Requirement: Offer preconditions
The *Commons Offer* workflow SHALL refuse, with a recorded reason, a workflow that is not
`commons_exportable`, whose version or ancestry the leak guard kept or could not check, that has
fewer than `MIN_RUNS_TO_OFFER` (5) runs, or whose current version does not have `public` in
`share_with` at publish time. A workflow whose `tainted_by` holds an observed (or unknown) sphere
SHALL need the owner's approval whatever the trust level.

#### Scenario: Too few runs
- **WHEN** the workflow has 4 recorded runs
- **THEN** the offer ends `refused` with a reason naming the runs and nothing is published

#### Scenario: Observed taint
- **WHEN** the workflow was shaped on an observed work device and the owner's `sharing` level is autonomous
- **THEN** the offer waits for the owner's approval

#### Scenario: Approval no longer current
- **WHEN** the workflow is saved again after approval, so `share_with` is reset
- **THEN** `commons_publish` refuses because `public` is not in `share_with`

### Requirement: Publishing and receipts
The publisher SHALL publish the signing device's certs and then the `OFFER` to the canonical relay
(the first of `COMMONS_RELAYS`) and to each mirror, and SHALL record every event it publishes and
every receipt it relies on in the local mirror. Receipts SHALL be trusted only from
`COMMONS_RECEIPT_PUBKEY`.

#### Scenario: Offer with receipt
- **WHEN** the owner approves an offer of a workflow with 5 runs
- **THEN** exactly one `OFFER` is on the relay, a receipt signed by the operator key names it, and the offer verifies against the Zebra's npub

### Requirement: Local mirror
`CommonsEventModel` SHALL store each published or relied-on Commons event once (`event_id`,
`kind`, `pubkey`, `created_at`, `relay_seq`, `content`, `sig`, `user_id` = the Commons owner) and
SHALL refuse updates and deletes.

#### Scenario: Append-only
- **WHEN** code tries to change or delete a stored row
- **THEN** it raises and the row is unchanged

### Requirement: Off by default
The publisher SHALL be built and injected only when the Commons is enabled, `COMMONS_RELAYS` is
set and the device has a Zebra identity and device key. The deploy job SHALL NOT install or start
the public relay units.

#### Scenario: Relays unset
- **WHEN** `ZEBRA_COMMONS_RELAYS` is unset
- **THEN** the engine has no `__commons_publisher__` and no relay connection is made

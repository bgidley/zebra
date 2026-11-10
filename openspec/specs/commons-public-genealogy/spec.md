# commons-public-genealogy Specification

## Purpose
TBD - created by archiving change commons-public-genealogy. Update Purpose after archive.

## Requirements

### Requirement: Built only from public events
The public genealogy SHALL be built only from `OFFER`, `ATTEST`, `TRUST` and `DEVICE_CERT` events
held in the local Commons mirror, plus this Zebra's local trust paths and peer display names. It
SHALL NOT read the lineage journal, workflow library files, private ancestors, `SKILL` events or
run data.

#### Scenario: Private ancestors are never shown
- **WHEN** the library holds private versions and journal records before a publicly offered
  version, and the mirror holds a `SKILL` event
- **THEN** no hash of a private version, journal record or `SKILL` event appears in the rendered
  public genealogy pages

#### Scenario: A parent that was never offered
- **WHEN** a mirrored `OFFER` carries a `parent` tag whose hash is not an `OFFER` in the mirror
- **THEN** no edge is drawn and that hash is not rendered anywhere

### Requirement: Workflow lineage across Zebras
The page SHALL show every offered content hash once, linked to its parent offer by the `parent`
tag, with its publishers (npub, fingerprint, display name), the number of distinct Zebras that
attested `adopted`, worked and failed run counts, and rejections, each attestation with its fixed
reason.

#### Scenario: Two-Zebra derivation
- **WHEN** Zebra B adopts Zebra A's offer, derives a new version and offers it, and A's mirror
  holds both offers and B's attestations
- **THEN** A's public genealogy shows A's offer → B's offer, B as publisher of the second, an
  adoption count of 1 on A's offer and B's attestations with their reasons

### Requirement: Parent named only if publicly offered
An `OFFER` SHALL carry a `parent` tag only when the parent hash was itself publicly offered by any
Zebra, as shown by an `OFFER` of that hash in the publisher's mirror. A private ancestor SHALL never
be named, not even by hash.

#### Scenario: Derived from another Zebra's offer
- **WHEN** B's workflow's parent is the hash of A's offer held in B's mirror
- **THEN** B's `OFFER` names that hash as `parent`

#### Scenario: Private parent
- **WHEN** the parent hash is not an `OFFER` in the mirror
- **THEN** B's `OFFER` has no `parent` tag

### Requirement: Zebra lineage
The page SHALL show who vouched for whom from the latest mirrored `TRUST` per pair (weight and
reason) and this Zebra's trust paths in the form "B via A: 0.8 × 0.6 × 0.9 = 0.43". It SHALL show
no market price history.

#### Scenario: Vouch and path
- **WHEN** the mirror holds A's `TRUST` in B and this Zebra's local trust has a path to B via A
- **THEN** the page lists A → B with its weight and reason, and the path text for B

### Requirement: Pages, access and default
`/commons/genealogy/` and `/commons/genealogy/<content_sha256>/` SHALL be behind login,
server-rendered with inline SVG through the renderer shared with the private genealogy. With the
Commons off the page SHALL show an empty state and read nothing; the per-offer page SHALL return
404 for a hash that is not an offer in the mirror.

#### Scenario: Commons off
- **WHEN** `COMMONS_ENABLED` is false
- **THEN** `/commons/genealogy/` shows that the Commons is off and no mirror is read

#### Scenario: Anonymous visitor
- **WHEN** a signed-out visitor requests either page with the production middleware
- **THEN** they are redirected to the login page

#### Scenario: Unknown hash
- **WHEN** the per-offer page is requested for a hash that is not an offer in the mirror
- **THEN** the response is 404

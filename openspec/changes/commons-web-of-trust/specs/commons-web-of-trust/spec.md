## ADDED Requirements

### Requirement: Off by default
The Zebra SHALL NOT publish or fetch `TRUST` events unless the Commons is enabled,
`ZEBRA_COMMONS_RELAYS` is set and the device has a Zebra identity and device key. Local trust
SHALL still be computed from the edges and vouches held locally.

#### Scenario: Relays unset
- **WHEN** `ZEBRA_COMMONS_RELAYS` is unset and the owner vouches for a Zebra
- **THEN** the vouch and its edge are stored locally, local trust is recomputed, and no relay is
  contacted

### Requirement: TRUST events
A `TRUST` event SHALL be kind 30233 with tags exactly `d` and `p` (the target Zebra), `zebra`
(the trusting Zebra), `t` and `v`, and content `{reason, weight}` with weight in -1..1. It SHALL be
signed by a device key attributed to the trusting Zebra by a valid `DEVICE_CERT`. Readers SHALL
refuse any other shape.

#### Scenario: Valid trust event
- **WHEN** a certified device of Zebra A signs `TRUST` weight 0.6 for Zebra B
- **THEN** `verify_trust` accepts it as the edge A→B with weight 0.6

#### Scenario: Tampered or misattributed
- **WHEN** the content, tags or signature are changed, the weight is outside -1..1, or the device
  has no cert from the `zebra` key
- **THEN** `verify_trust` refuses it and no edge is stored

### Requirement: Latest edge wins
For each pair (from, to) only the latest edge SHALL be kept: by receipt order when both events
have a receipt, otherwise by `created_at`.

#### Scenario: Older edge arrives later
- **WHEN** an older `TRUST` for a pair arrives after a newer one
- **THEN** the stored edge is unchanged

### Requirement: Human vouching
Only the owner SHALL vouch for, withdraw from or distrust a Zebra. Vouching SHALL set
`vouched_by_user` and the edge weight 0.8; withdrawing weight 0; distrusting a negative weight.
Each SHALL publish a `TRUST` event when publishing is on. No LLM SHALL set trust.

#### Scenario: Owner vouches
- **WHEN** the owner chooses "I know this Zebra" for Zebra A
- **THEN** A is a vouched seed with edge weight 0.8 and a `TRUST` event for A is published

#### Scenario: Someone else tries
- **WHEN** a signed-in user who is not the owner posts a vouch
- **THEN** the response is 403 and nothing changes

### Requirement: Experience
Each of this Zebra's own attestations about a publisher's workflow SHALL update its edge to that
publisher by EWMA (worked raises; failed, rejected-ethics, rejected-gym and pii-found lower). The
owner's vouch SHALL be a floor the EWMA cannot lower the weight below. A new weight SHALL be
published only when it differs from the last published weight by at least 0.1.

#### Scenario: Failures on a vouched peer
- **WHEN** this Zebra attests `failed` many times on workflows of a vouched publisher
- **THEN** its edge stays at 0.8

#### Scenario: Small change
- **WHEN** an attestation moves the edge by less than 0.1 from the last published weight
- **THEN** no `TRUST` is published

### Requirement: Transitive local trust
Local trust SHALL be `max over paths p of ∏ weights × 0.9^(hops-1)` over paths of at most 3 hops
starting at a human-vouched seed, with negative edges only as the last hop and this Zebra's own
negative edge taking precedence. A Zebra with no path from a vouched seed SHALL have trust 0. The
result SHALL be deterministic and the best path SHALL be shown.

#### Scenario: Two hops
- **WHEN** the owner vouches A (0.8) and A trusts B (0.6)
- **THEN** B's local trust is 0.8 × 0.6 × 0.9 = 0.432 and the page shows "B via A"

#### Scenario: Sybil
- **WHEN** Zebras that no vouched seed reaches trust each other highly
- **THEN** each has local trust 0

#### Scenario: Too far
- **WHEN** the only path to Z has four hops
- **THEN** Z's local trust is 0

### Requirement: Import score
Every offer SHALL have an import score `0.7·local_trust(publisher) + 0.3·attestation_signal`,
where the signal is the trust-weighted mean of worked (+1) and failed (-1) attestations from other
Zebras. Offers below `IMPORT_SCORE_THRESHOLD` 0.5 SHALL never be judged automatically, and the
owner's **Import this** SHALL show the score and warn below it.

#### Scenario: Unconnected publisher
- **WHEN** an offer comes from a Zebra with no path from a vouched seed and no trusted reporters
- **THEN** its score is 0 and `/commons/` flags it below the threshold

### Requirement: Peers section
`/commons/` SHALL list peers with local trust, vouch state, best path and edges in and out, with
Zebra's reasoning in its own voice, owner-only actions and empty states, readable at phone width.

#### Scenario: No peers
- **WHEN** no peer is known
- **THEN** the section says so and, for the owner, offers "I know this Zebra" by npub

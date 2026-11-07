## MODIFIED Requirements

### Requirement: Commons client
The Commons SHALL be reached only through a `CommonsClient` with `publish`, `subscribe` and
`fetch`. An in-memory implementation SHALL exist for tests, and every client SHALL refuse to
publish a `SKILL` event to a relay that is not private. A client for a public relay SHALL also
refuse every event whose kind is not one of the public Commons kinds or that is not tagged
`["t","zebra-commons"]`.

#### Scenario: SKILL refused on a public relay
- **WHEN** a `SKILL` event is published to a non-private relay
- **THEN** publishing raises and the relay stores nothing

#### Scenario: Non-public kind refused on a public relay
- **WHEN** an event of a kind that is not public is published to a non-private relay
- **THEN** publishing raises and the relay stores nothing

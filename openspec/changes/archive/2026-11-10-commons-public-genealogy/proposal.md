## Why

The private genealogy (#238) shows a workflow's family tree on this device. Once Zebras offer,
adopt and attest workflows publicly (S4 #231, S5 #232) and vouch for each other (S6 #233), the
owner should also see the **public** family tree of a skill across Zebras and how Zebras are linked,
without anything private leaking into it. This change (GitLab #247, epic #41) adds
`/commons/genealogy/`, built **only from public Commons events in the local mirror**. It ships as
code, off by default: with no relays configured the page shows what the mirror holds (nothing on
prod today) or an empty state.

## What Changes

- **Read model** (`zebra_agent/commons/public_genealogy.py`, no Django): `build_public_genealogy(
  events, me, names=, trust_paths=)` over mirrored events of the public kinds `OFFER`, `ATTEST`,
  `TRUST`, `DEVICE_CERT` only. Workflow lineage: one node per offered content hash, edges from the
  `parent` tag (only when the parent is itself an offer in the mirror), publishers (npub,
  fingerprint, peer display name), adoption count (distinct Zebras attesting `adopted`), worked /
  failed runs and rejections with their fixed-vocabulary reasons. Zebra lineage: who vouched for
  whom (latest `TRUST` per pair) and this Zebra's trust paths from S6 (`path_text`).
- **Public parent rule widened**: an `OFFER` names its `parent` when that parent was publicly
  offered by **any** Zebra (an `OFFER` in this Zebra's mirror), not only by this Zebra. A Zebra that
  adopts A's offer and derives a new version now links back to A's offer; a private ancestor is
  still never named, not even by hash (`CommonsMirror.public_hashes`).
- **Shared DAG renderer**: #238's inline-SVG renderer and layered layout are split out
  (`api/dag_svg.py`, `genealogy.layer_dag`) and used by both the private page and the public one.
- **Pages**: `/commons/genealogy/` (lineage DAG of every public offer, offer list, vouching graph
  and list, my trust paths) and `/commons/genealogy/<content_sha256>/` (one offer's family, its
  publisher, adoptions and attestations). Server-rendered, theme tokens, light / dark, Zebra's voice,
  WCAG AA, phone width without horizontal scroll, behind login.
- **No market price history** (S7 parked, #234); no `GRANT` (none exist yet).

## Capabilities

### New Capabilities
- `commons-public-genealogy`: the public genealogy read model, its privacy rule, and the two pages.

### Modified Capabilities
- (none: the widened parent rule is recorded in this change's spec)

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Nothing private reaches the public genealogy: only `OFFER` / `ATTEST` / `TRUST` / `DEVICE_CERT` events from the mirror are read; no hash of a private ancestor, journal entry, library file, `SKILL` event or run appears in the page, and a parent is shown only if it is itself a public offer | Test seeding private ancestors (library files + lineage journal + a `SKILL` event + a forged private `parent` tag) asserts none of their hashes is in the rendered HTML of either page |
| O2 | In-memory two-Zebra E2E: B adopts A's offer, derives and offers a new version; A's public genealogy shows A's offer → B's derived offer, with B's adoption and attestation and B as publisher, and no private ancestor hashes | `zebra-agent/tests/test_commons_two_zebras.py` (real *Commons Import*) and the web E2E rendering A's page |
| O3 | Zebra lineage shows who vouched for whom from mirrored `TRUST` events (latest per pair, weight and reason) and this Zebra's trust paths in S6's form ("B via A: 0.8 × 0.6 × 0.9 = 0.43") | Read-model and page tests with A vouching B and a computed path |
| O4 | Off by default and safe: with the Commons off the page says so and reads nothing; with no relays it shows the mirror (or an empty state); both pages are behind login (prod middleware) and the per-offer page 404s for an unknown or private hash | Page tests (off, empty, populated, 404, anonymous → login) |
| O5 | The private page still renders through the shared renderer (no copy), and the public pages work at 390 px with no horizontal scroll, light and dark, AA contrast | Existing #238 tests pass unchanged; Playwright container check at 390 px (light + dark) recorded in `tasks.md` |

> Branch: `f247/public-genealogy`. Commit with `Refs #247` (do not close #247: it closes with the
> live two-Zebra run).

## 1. Core (zebra-agent, no Django)

- [x] 1.1 `genealogy.layer_dag()` shared layout; `_layout` uses it
- [x] 1.2 `CommonsMirror.public_hashes()`; `public_parent` fed by it in `CommonsPublisher.build` and `commons_prepare_offer`
- [x] 1.3 `commons/public_genealogy.py`: `build_public_genealogy`, `PublicOffer`, `TrustLink`, `PublicGenealogy.family()`
- [x] 1.4 Tests: kinds filter, parent only between held offers, publishers, adoption / attestation counts, latest trust per pair, family; two-Zebra E2E (real *Commons Import*, derived offer)

## 2. Web

- [x] 2.1 `api/dag_svg.py` shared renderer; `genealogy_svg` uses it
- [x] 2.2 `api/public_genealogy_view.py` context; views `commons_genealogy`, `commons_genealogy_offer`; URLs
- [x] 2.3 Templates `pages/commons_genealogy.html`, `pages/commons_genealogy_offer.html`; link from `/commons/`
- [x] 2.4 Tests: off, empty, populated, per-offer, 404, privacy (private ancestors, journal, SKILL, forged parent), login with prod middleware, web two-Zebra E2E
- [x] 2.5 Playwright container check (390 px, light + dark), recorded here
  - 2026-11-09, `mcr.microsoft.com/playwright/python:v1.55.0-noble`, local server on 127.0.0.1:8471
    (throwaway SQLite, Commons on, no relays, daemon off) seeded with three Zebras: four offers
    (one derived across Zebras, a second derivation, an unrelated one), seven attestations, three
    `TRUST` links (one negative, one owner note, a cycle), two peers with stored best paths.
  - Chromium and WebKit at 390 x 844, dark and light, both pages:
    HTTP 200, `scrollWidth == clientWidth` (390 / 382), 2 graphs on the index (4 node links),
    1 on the offer page (3 node links). Screenshots read: labels legible, npubs wrap, no overflow.
  - Fix from the check: node second lines shortened to "by <publisher>" (were cut off) and a
    Zebra with no display name no longer repeats its fingerprint.

## 3. Docs

- [x] 3.1 `zebra-commons-design.md`, `zebra-as-is.md`, AGENTS files

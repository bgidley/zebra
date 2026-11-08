> Branch: `f233/commons-trust`. Commit with `Refs #233` (do not close #233: the live check in the
> runbook closes it).

## 1. Core (zebra-agent, no Django)

- [x] 1.1 `commons/trust.py`: `build_trust` / `verify_trust`, reasons, `compute_trust`, EWMA, `import_score`, `attestation_signal`, `path_text`
- [x] 1.2 `commons/peers.py`: `PeerRecord`, `TrustEdge`, `is_newer`, `TrustStore` + `InMemoryTrustStore`
- [x] 1.3 `commons/web_of_trust.py` `WebOfTrust`: vouch / withdraw / distrust, `record_experience`, `publish_pending`, `ingest`, `recompute`, `score`
- [x] 1.4 `CommonsExchange`: `trust` attribute, `fetch_trust` in `poll()`, experience after `attest`
- [x] 1.5 Tests: paths (0.8 × 0.6 with decay, max, length cap, negative one-hop, Sybil zero, determinism), EWMA + floor + threshold, build/verify, latest wins, import score; in-memory multi-Zebra E2E

## 2. Web (off by default)

- [x] 2.1 `PeerModel`, `TrustEdgeModel`, migration; `DjangoPeerTrustStore`
- [x] 2.2 Wiring: `build_commons_exchange` adds the `WebOfTrust`; local-only service when publishing is off
- [x] 2.3 `/commons/` peers section + owner-only vouch / withdraw / distrust; scores on offers with the warning
- [x] 2.4 Tests: wiring off, page (off, empty, peers, best path, owner-only, score warning)
- [x] 2.5 Playwright container check (phone width), recorded

## 3. Integration + docs

- [x] 3.1 Gated podman strfry test: TRUST published, fetched by another Zebra, local trust computed
- [x] 3.2 Runbook live check; `zebra-commons-design.md`, `zebra-as-is.md`, AGENTS files

## Phone-width check (recorded 2026-11-08)

Local server on 127.0.0.1:8765 (throwaway SQLite settings, `COMMONS_ENABLED`, relays unset,
`ZEBRA_DAEMON_AUTO_START=0`), seeded with a vouched A, A→B 0.6, B→C 0.5, A→stranger -0.5 and an
offer from the stranger. Playwright container `mcr.microsoft.com/playwright/python:v1.55.0-noble`:

| Browser | Viewport | Peers | scrollWidth = innerWidth | Vouch form visible | Score warning |
|---|---|---|---|---|---|
| Chromium | 390 × 844 | 4 | 390 = 390 (no horizontal scroll) | yes | yes |
| WebKit | iPad (gen 7) | 4 | 810 = 810 | yes | yes |

Paths shown: `Alice's Zebra directly: 0.8 = 0.80`, `EAEN-POFR via Alice's Zebra: 0.8 × 0.6 × 0.9
= 0.43`, `PBEC-AOP7 via Alice's Zebra → EAEN-POFR: 0.8 × 0.6 × 0.5 × 0.9^2 = 0.19`,
`ST4K-C7WN via Alice's Zebra: 0.8 × -0.5 × 0.9 = -0.36`. Long npubs wrap (`break-all`); owner
buttons wrap below each card.

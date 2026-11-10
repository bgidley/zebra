## Context

#238 built the private genealogy (`zebra_agent/genealogy.py`, `api/genealogy_view.py`). S4–S6
built the public events and the local mirror (`CommonsEventModel`, append-only, holding only events
this Zebra published or verified at intake), the offer store and the web of trust (`PeerModel`,
`TrustEdgeModel`, `compute_trust`, `path_text`). This change reads them; it publishes nothing.

## Goals / Non-Goals

**Goals:** `/commons/genealogy/` and the per-offer page from public events only; the privacy rule
enforced in code and tests; reuse of #238's renderer.

**Non-Goals:** market prices (S7 parked, #234); `GRANT` (no such events yet); fetching from relays
on page load (the daemon's exchange fills the mirror); any change to what is published other than
the widened parent rule.

## Decisions

- **Source of truth = mirror, public kinds only.** `build_public_genealogy` takes events and drops
  every kind outside `{OFFER, ATTEST, TRUST, DEVICE_CERT}` before reading anything. It never takes a
  library, journal, offer store row or run. The web view passes `mirror.events(kind=…)` per kind.
- **Nodes are offered hashes.** Key = the `d` tag (64 lowercase hex). The same hash offered by
  several Zebras is one node with several publishers (earliest first); a Zebra re-offering the same
  hash counts once. Content shown: name, summary, `stats`, publishers, offered time. The offer's
  YAML is not shown.
- **Edges only between held offers.** `parent` → child is drawn only when the parent hash is itself
  an `OFFER` in the mirror. A `parent` tag naming anything else is ignored and never rendered
  (defence in depth: an older or hostile Zebra could tag a private hash).
- **Attestations attach only to held offers.** `ATTEST`s whose `x` is not an offered hash are
  ignored. Counts: `adopted` / `rejected` = distinct Zebras, `worked` / `failed` = events; items
  carry label, Zebra, fixed reason and time (reuses `exchange.attestation_summary`).
- **Trust edges.** Latest `TRUST` per (from, to) by `created_at`, then event id (the mirror holds
  only verified ones); zero weight = withdrawn, shown as such in the list, not drawn. Paths come
  from S6's stored `best_path` per peer (`PeerModel`) and are formatted with `path_text`.
- **Names.** Peer display names from `PeerModel` (local labels for public keys), else fingerprint;
  this Zebra is "me".
- **Parent rule widened** (`offer.public_parent`): "publicly offered" = an `OFFER` of that hash in
  this Zebra's mirror (own or verified intake), via `CommonsMirror.public_hashes()`. This is what
  makes B's derived offer link to A's. Still never a private hash.
- **Renderer shared.** `genealogy.layer_dag(parents, order_key)` (longest-path layers, cycle-safe)
  and `api/dag_svg.py` `DagNode` + `dag_svg(nodes, edges, label)`; `genealogy_svg` becomes a thin
  adapter. Edges may be dashed (negative trust).
- **Off by default.** Commons off → empty state, no DB read. No relays → whatever the mirror holds.
  Per-offer page: 404 for a hash that is not an offer in the mirror.

## Risks / Trade-offs

- A large Commons makes a wide SVG; it scales down (`max-width: 100%`) and the list below carries
  the same facts with links, so the page stays usable. Paging is deferred until the Commons is live.
- Trust paths are this Zebra's own reckoning (S6), shown here because the issue asks for them; they
  reveal only public keys and weights.

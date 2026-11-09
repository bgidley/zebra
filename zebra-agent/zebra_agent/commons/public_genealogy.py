"""Public skill genealogy (#247): the Commons family tree, from public events only.

``build_public_genealogy(events, me)`` reads mirrored Commons events and returns:

- **Workflow lineage across Zebras:** one node per publicly offered content hash (the ``OFFER``'s
  ``d`` tag), linked to its parent offer by the ``parent`` tag, with its publishers, the number of
  Zebras that adopted it and the worked / failed / rejected attestations with their fixed reasons.
- **Zebra lineage:** who vouched for whom (the latest ``TRUST`` per pair) and how many certified
  devices each Zebra has.

**Privacy rule.** Only ``PUBLIC_GENEALOGY_KINDS`` are read; every other event is dropped before
anything is looked at. Nothing here takes a library, the lineage journal, a ``SKILL`` event or run
data, so a private ancestor cannot be shown or referenced, not even by hash. A ``parent`` tag is
drawn only when the parent is itself an ``OFFER`` held here, and an ``ATTEST`` counts only on a
held offer: a hash that was never publicly offered is never rendered.

No Django, no network: the web page (``zebra_agent_web.api.public_genealogy_view``) lays it out.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from zebra_agent.commons.attest import REASONS
from zebra_agent.commons.events import Event
from zebra_agent.commons.exchange import attestation_summary, empty_summary
from zebra_agent.commons.kinds import ATTEST_KIND, DEVICE_CERT_KIND, OFFER_KIND, TRUST_KIND
from zebra_agent.genealogy import layer_dag

#: The only event kinds the public genealogy reads (#247 privacy rule).
PUBLIC_GENEALOGY_KINDS = frozenset({OFFER_KIND, ATTEST_KIND, TRUST_KIND, DEVICE_CERT_KIND})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _one(event: Event, name: str) -> str | None:
    values = event.tag_values(name)
    return values[0] if len(values) == 1 and _HEX64.match(values[0] or "") else None


@dataclass
class PublicOffer:
    """One publicly offered version (content hash) of a workflow."""

    content_sha256: str
    name: str
    summary: str
    stats: dict[str, Any]
    publishers: list[str]  # Zebra pubkeys, earliest offer first
    offered_at: int  # the earliest offer of this hash
    parent: str | None = None  # only a held offer
    children: list[str] = field(default_factory=list)
    attestations: dict[str, Any] = field(default_factory=empty_summary)
    layer: int = 0
    order: int = 0

    @property
    def short(self) -> str:
        return self.content_sha256[:12]

    @property
    def publisher(self) -> str:
        return self.publishers[0]


@dataclass(frozen=True)
class TrustLink:
    """The latest ``TRUST`` from one Zebra in another."""

    from_pubkey: str
    to_pubkey: str
    weight: float
    reason: str
    created_at: int


@dataclass
class PublicGenealogy:
    """What ``build_public_genealogy`` returns."""

    me: str | None
    offers: list[PublicOffer]  # oldest first
    edges: list[tuple[str, str]]  # (parent hash, child hash)
    trust: list[TrustLink]  # latest per pair, zero weights included (withdrawn)
    devices: dict[str, int] = field(default_factory=dict)  # Zebra → certified devices held

    @property
    def layers(self) -> int:
        return max((o.layer for o in self.offers), default=-1) + 1

    def offer(self, content_sha256: str) -> PublicOffer | None:
        return next((o for o in self.offers if o.content_sha256 == content_sha256), None)

    @property
    def zebras(self) -> list[str]:
        """Every Zebra the genealogy names: publishers, attesters and trust ends."""
        seen: dict[str, None] = {}
        for o in self.offers:
            for z in o.publishers:
                seen[z] = None
            for item in o.attestations["items"]:
                seen[item["zebra_pubkey"]] = None
        for t in self.trust:
            seen[t.from_pubkey] = None
            seen[t.to_pubkey] = None
        return list(seen)

    def family(self, content_sha256: str) -> PublicGenealogy | None:
        """The offers linked to *content_sha256* by parent / child, laid out on their own."""
        start = self.offer(content_sha256)
        if start is None:
            return None
        by_key = {o.content_sha256: o for o in self.offers}
        found, todo = set(), [start.content_sha256]
        while todo:
            key = todo.pop()
            if key in found:
                continue
            found.add(key)
            o = by_key[key]
            todo += [k for k in [o.parent, *o.children] if k and k in by_key]
        offers = [
            PublicOffer(**{**o.__dict__, "children": list(o.children)})
            for o in self.offers
            if o.content_sha256 in found
        ]
        _place(offers)
        edges = [(p, c) for p, c in self.edges if p in found and c in found]
        trust = [t for t in self.trust if t.from_pubkey in found or t.to_pubkey in found]
        return PublicGenealogy(self.me, offers, edges, trust, dict(self.devices))


def _place(offers: list[PublicOffer]) -> None:
    by_key = {o.content_sha256: o for o in offers}
    placed = layer_dag(
        {o.content_sha256: [o.parent] if o.parent in by_key else [] for o in offers},
        lambda k: (by_key[k].offered_at, k),
    )
    for key, (layer, order) in placed.items():
        by_key[key].layer, by_key[key].order = layer, order


def public_events(events: Iterable[Event]) -> list[Event]:
    """*events* of the public genealogy kinds only; everything else is dropped unread."""
    return [e for e in events if e.kind in PUBLIC_GENEALOGY_KINDS]


def _offers(events: list[Event]) -> dict[str, PublicOffer]:
    out: dict[str, PublicOffer] = {}
    pending_parent: dict[str, str] = {}
    for event in sorted(events, key=lambda e: (e.created_at, e.id)):
        if event.kind != OFFER_KIND:
            continue
        sha, zebra = _one(event, "d"), _one(event, "zebra")
        if sha is None or zebra is None or event.tag_values("x") != [sha]:
            continue
        content = event.json_content() or {}
        stats = content.get("stats") if isinstance(content.get("stats"), dict) else {}
        row = out.get(sha)
        if row is None:
            row = out[sha] = PublicOffer(
                content_sha256=sha,
                name=" ".join(str(content.get("name") or "").split())[:200] or "untitled",
                summary=" ".join(str(content.get("summary") or "").split())[:2000],
                stats={
                    k: stats.get(k) for k in ("runs", "success_rate", "avg_rating", "gym_score")
                },
                publishers=[zebra],
                offered_at=event.created_at,
            )
        elif zebra not in row.publishers:
            row.publishers.append(zebra)
        parent = _one(event, "parent")
        if parent and parent != sha and sha not in pending_parent:
            pending_parent[sha] = parent
    for sha, parent in pending_parent.items():
        if parent in out:  # never a hash that is not itself a held offer
            out[sha].parent = parent
            out[parent].children.append(sha)
    return out


def _trust(events: list[Event]) -> list[TrustLink]:
    latest: dict[tuple[str, str], tuple[tuple[int, str], TrustLink]] = {}
    for event in events:
        if event.kind != TRUST_KIND:
            continue
        target, zebra = _one(event, "d"), _one(event, "zebra")
        content = event.json_content() or {}
        weight = content.get("weight")
        if target is None or zebra is None or target == zebra:
            continue
        if isinstance(weight, bool) or not isinstance(weight, int | float):
            continue
        if not -1 <= weight <= 1:
            continue
        link = TrustLink(
            zebra,
            target,
            round(float(weight), 2),
            " ".join(str(content.get("reason") or "").split())[:140],
            event.created_at,
        )
        order = (event.created_at, event.id)
        current = latest.get((zebra, target))
        if current is None or order > current[0]:
            latest[(zebra, target)] = (order, link)
    return [v[1] for _, v in sorted(latest.items())]


def _devices(events: list[Event]) -> dict[str, int]:
    held: dict[str, set[str]] = {}
    for event in events:
        if event.kind == DEVICE_CERT_KIND:
            device = _one(event, "d")
            if device:
                held.setdefault(event.pubkey, set()).add(device)
    return {zebra: len(devices) for zebra, devices in sorted(held.items())}


def build_public_genealogy(events: Iterable[Event], me: str | None) -> PublicGenealogy:
    """The public genealogy from mirrored *events* (any kinds; only the public ones are read).

    *me* is this Zebra's pubkey (None before it has one).
    """
    events = public_events(events)
    offers = _offers(events)
    attests = attestation_summary(
        [e for e in events if e.kind == ATTEST_KIND and _one(e, "x") in offers]
    )
    for sha, summary in attests.items():
        for item in summary["items"]:  # only the fixed vocabulary is ever shown
            if item["reason"] not in REASONS.get(item["label"], ()):
                item["reason"] = None
        offers[sha].attestations = summary
    ordered = sorted(offers.values(), key=lambda o: (o.offered_at, o.content_sha256))
    _place(ordered)
    edges = [(o.parent, o.content_sha256) for o in ordered if o.parent]
    return PublicGenealogy(me, ordered, edges, _trust(events), _devices(events))

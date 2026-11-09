"""The public genealogy pages (#247): ``/commons/genealogy/`` and one offer's family.

Built only from public events in the local mirror (``zebra_agent.commons.public_genealogy``):
the mirror is read one public kind at a time, so no other kind is ever loaded. Peer display
names and this Zebra's trust paths (S6) come from ``PeerModel``. Nothing here reads the
library, the lineage journal, ``SKILL`` events or runs, and nothing contacts a relay.
Graphs are drawn by the renderer shared with the private genealogy (``api/dag_svg.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.urls import reverse
from zebra_agent.commons import keys
from zebra_agent.commons.identity import fingerprint
from zebra_agent.commons.public_genealogy import (
    PUBLIC_GENEALOGY_KINDS,
    PublicGenealogy,
    PublicOffer,
    build_public_genealogy,
)
from zebra_agent.commons.trust import TrustPath, path_text
from zebra_agent.genealogy import layer_dag

from zebra_agent_web.api.dag_svg import DagEdge, DagNode, dag_svg

#: Attestation labels as the page names them.
LABEL_TEXT = {
    "adopted": "adopted",
    "worked": "worked",
    "failed": "failed",
    "rejected-ethics": "rejected (ethics)",
    "rejected-gym": "rejected (golden tasks)",
    "rejected-pii": "rejected (scan could not run)",
    "pii-found": "rejected (personal data)",
}
#: The fixed attestation reasons, in plain words.
REASON_TEXT = {
    "passed-checks": "passed every check",
    "owner-approved": "its owner approved it",
    "ethics-review": "the ethics review turned it down",
    "golden-tasks-failed": "it failed the golden tasks",
    "scan-failed-closed": "the personal-data scan could not run",
    "personal-data": "the scan found personal data",
    "run-succeeded": "a run succeeded",
    "run-failed": "a run failed",
}
#: Fixed ``TRUST`` reasons, in plain words; anything else is the owner's own note.
TRUST_REASON_TEXT = {
    "vouched": "vouched",
    "withdrawn": "withdrew",
    "distrusted": "distrusts",
    "experience": "from its own runs",
}


def _when(timestamp: int | None) -> datetime | None:
    return datetime.fromtimestamp(timestamp, UTC) if timestamp else None


def offer_url(content_sha256: str) -> str:
    return reverse("commons_genealogy_offer", args=[content_sha256])


class _Names:
    """Labels for Zebra keys: "me", the peer's display name, else the fingerprint."""

    def __init__(self, me: str | None, display: dict[str, str]):
        self.me, self.display = me, display

    def name(self, pubkey: str) -> str:
        if pubkey == self.me:
            return "me"
        return self.display.get(pubkey) or fingerprint(pubkey)

    def label(self, pubkey: str) -> dict[str, Any]:
        return {
            "pubkey": pubkey,
            "npub": keys.npub_encode(pubkey),
            "fingerprint": fingerprint(pubkey),
            "name": self.name(pubkey),
            "display_name": self.display.get(pubkey, ""),
            "is_me": pubkey == self.me,
        }


def _clip(text: str, limit: int = 18) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def offers_svg(genealogy: PublicGenealogy, names: _Names, *, focus: str | None = None) -> str:
    """The workflow lineage across Zebras: one node per offered hash, parents above."""
    nodes = []
    for o in genealogy.offers:
        adopted = o.attestations["adopted"]
        mine = o.publisher == names.me
        title = (
            f"{o.short}, {o.name}, offered by {names.name(o.publisher)}"
            f", adopted by {adopted} Zebra{'s' if adopted != 1 else ''}"
        )
        nodes.append(
            DagNode(
                key=o.content_sha256,
                layer=o.layer,
                order=o.order,
                line1=o.short,
                line2=_clip(f"by {names.name(o.publisher)}"),
                title=title,
                href=offer_url(o.content_sha256),
                stroke="var(--color-ok)" if mine else "var(--color-muted)",
                strong=o.content_sha256 == focus,
            )
        )
    return dag_svg(
        nodes,
        [DagEdge(p, c) for p, c in genealogy.edges],
        f"Public lineage: {len(nodes)} offered version{'s' if len(nodes) != 1 else ''}",
        marker="pub-gen-arrow",
    )


def trust_svg(genealogy: PublicGenealogy, names: _Names) -> str:
    """Who vouched for whom: Zebras as nodes, current non-zero ``TRUST`` edges as arrows."""
    links = [t for t in genealogy.trust if t.weight]
    zebras = sorted({k for t in links for k in (t.from_pubkey, t.to_pubkey)})
    if not zebras:
        return ""
    parents = {z: [t.from_pubkey for t in links if t.to_pubkey == z] for z in zebras}
    placed = layer_dag(parents, lambda k: (k != names.me, names.name(k), k))
    nodes = [
        DagNode(
            key=z,
            layer=placed[z][0],
            order=placed[z][1],
            line1=_clip(names.name(z), 16),
            line2=fingerprint(z) if names.name(z) != fingerprint(z) else "Zebra",
            title=f"Zebra {names.name(z)} ({fingerprint(z)})",
            stroke="var(--color-ok)" if z == names.me else "var(--color-muted)",
            strong=z == names.me,
        )
        for z in zebras
    ]
    return dag_svg(
        nodes,
        [DagEdge(t.from_pubkey, t.to_pubkey, dashed=t.weight < 0) for t in links],
        f"Who vouched for whom: {len(links)} link{'s' if len(links) != 1 else ''}",
        marker="trust-arrow",
    )


def _offer_card(o: PublicOffer, names: _Names) -> dict[str, Any]:
    items = [
        {
            "label": i["label"],
            "label_text": LABEL_TEXT.get(i["label"], i["label"]),
            "reason": i["reason"],
            "reason_text": REASON_TEXT.get(i["reason"] or "", ""),
            "zebra": names.label(i["zebra_pubkey"]),
            "created_on": _when(i["created_at"]),
            "kind": (
                "ok"
                if i["label"] in ("adopted", "worked")
                else "fail"
                if i["label"] == "failed"
                else "rejected"
            ),
        }
        for i in o.attestations["items"]
    ]
    return {
        "content_sha256": o.content_sha256,
        "short": o.short,
        "url": offer_url(o.content_sha256),
        "name": o.name,
        "summary": o.summary,
        "stats": o.stats,
        "publishers": [names.label(p) for p in o.publishers],
        "mine": o.publisher == names.me,
        "offered_on": _when(o.offered_at),
        "parent": {"short": o.parent[:12], "url": offer_url(o.parent)} if o.parent else None,
        "children": [{"short": c[:12], "url": offer_url(c)} for c in o.children],
        "adopted": o.attestations["adopted"],
        "rejected": o.attestations["rejected"],
        "worked": o.attestations["worked"],
        "failed": o.attestations["failed"],
        "items": items,
    }


def _trust_rows(genealogy: PublicGenealogy, names: _Names) -> list[dict[str, Any]]:
    rows = []
    for t in sorted(genealogy.trust, key=lambda t: (-abs(t.weight), t.from_pubkey, t.to_pubkey)):
        fixed = t.reason in TRUST_REASON_TEXT
        rows.append(
            {
                "from": names.label(t.from_pubkey),
                "to": names.label(t.to_pubkey),
                "weight": t.weight,
                "withdrawn": t.weight == 0,
                "negative": t.weight < 0,
                "reason": TRUST_REASON_TEXT[t.reason] if fixed else t.reason,
                "note": not fixed,
                "set_on": _when(t.created_at),
            }
        )
    return rows


def _paths(peers, names: _Names) -> list[dict[str, Any]]:
    rows = []
    for peer in peers:
        path = TrustPath.from_dict(peer.best_path)
        if not path.hops or peer.pubkey == names.me:
            continue
        rows.append(
            {
                "zebra": names.label(peer.pubkey),
                "text": path_text(path, names.name),
                "value": path.value,
            }
        )
    rows.sort(key=lambda r: (-r["value"], r["zebra"]["pubkey"]))
    return rows


async def load_public_genealogy() -> tuple[PublicGenealogy, _Names, list]:
    """The genealogy from the mirror's public kinds, the names and the peers (DB only)."""
    from zebra_agent_web.api.commons_identity import get_owner_id
    from zebra_agent_web.api.models import SystemStateModel
    from zebra_agent_web.commons_mirror_store import DjangoCommonsMirror
    from zebra_agent_web.commons_peer_store import DjangoPeerTrustStore

    owner = await get_owner_id()
    state = await SystemStateModel.objects.filter(pk=1).afirst()
    me = (state.zebra_pubkey if state else "") or None
    mirror = DjangoCommonsMirror(owner)
    events = []
    for kind in sorted(PUBLIC_GENEALOGY_KINDS):  # never load any other kind
        events += [m.event for m in await mirror.events(kind=kind)]
    peers = await DjangoPeerTrustStore(owner).list_peers()
    names = _Names(me, {p.pubkey: p.display_name for p in peers if p.display_name})
    return build_public_genealogy(events, me), names, peers


async def public_genealogy_context() -> dict[str, Any]:
    """Template context for ``pages/commons_genealogy.html``."""
    from zebra_agent_web.api.commons_publish import publishing_configured

    genealogy, names, peers = await load_public_genealogy()
    cards = [_offer_card(o, names) for o in reversed(genealogy.offers)]  # newest first
    return {
        "enabled": True,
        "publishing_on": publishing_configured(),
        "has_identity": names.me is not None,
        "graph_svg": offers_svg(genealogy, names),
        "offers": cards,
        "offer_count": len(cards),
        "publisher_count": len({p for o in genealogy.offers for p in o.publishers}),
        "trust_svg": trust_svg(genealogy, names),
        "trust_rows": _trust_rows(genealogy, names),
        "paths": _paths(peers, names),
        "zebras": [
            {**names.label(z), "devices": genealogy.devices.get(z, 0)} for z in genealogy.zebras
        ],
    }


async def public_offer_context(content_sha256: str) -> dict[str, Any] | None:
    """Template context for ``pages/commons_genealogy_offer.html``; None if not an offer."""
    genealogy, names, _peers = await load_public_genealogy()
    family = genealogy.family(content_sha256)
    if family is None:
        return None
    offer = family.offer(content_sha256)
    return {
        "offer": _offer_card(offer, names),
        "graph_svg": offers_svg(family, names, focus=content_sha256),
        "family": [_offer_card(o, names) for o in family.offers],
        "family_count": len(family.offers),
    }

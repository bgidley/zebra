"""This Zebra's web of trust: vouching, experience, local trust (#233, S6).

``WebOfTrust`` owns a ``TrustStore``, this Zebra's key and, only when publishing is on, the
``CommonsPublisher``. Without a publisher every change is local: nothing is published or
fetched, and local trust is still computed from what is held.

- The owner (web view only): ``vouch`` (0.8, a seed), ``withdraw`` (0), ``distrust`` (-0.8).
- Experience: ``record_experience`` after each of this Zebra's own ``ATTEST``s
  (``CommonsExchange.attest``); published only past ``PUBLISH_THRESHOLD``.
- ``ingest`` stores verified ``TRUST`` events fetched by ``CommonsExchange.fetch_trust``;
  ``recompute`` refreshes every peer's local trust and best path.

No LLM is involved anywhere here.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from zebra_agent.commons.events import Event
from zebra_agent.commons.peers import PeerRecord, TrustEdge, TrustStore
from zebra_agent.commons.trust import (
    DISTRUST_WEIGHT,
    DISTRUSTED,
    EXPERIENCE,
    VOUCH_WEIGHT,
    VOUCHED,
    WITHDRAWN,
    TrustRefused,
    TrustVerification,
    attestation_signal,
    build_trust,
    canonical_weight,
    clean_reason,
    clears_threshold,
    compute_trust,
    experience_update,
    import_score,
    should_publish,
)

if TYPE_CHECKING:
    from zebra_agent.commons.publisher import CommonsPublisher

logger = logging.getLogger(__name__)

_KEY = re.compile(r"^[0-9a-f]{64}$")


def _now() -> int:
    return int(time.time())


@dataclass
class WebOfTrust:
    """Trust edges and local trust of one Zebra.

    Attributes:
        store: Peers and edges (``PeerModel`` / ``TrustEdgeModel`` on the web)
        zebra_pubkey: This Zebra's key
        publisher: Publishes ``TRUST`` events; None while publishing is off
        clock: Seconds since the epoch (tests)
    """

    store: TrustStore
    zebra_pubkey: str
    publisher: CommonsPublisher | None = None
    clock: Callable[[], int] = field(default=_now, repr=False)

    @property
    def publishing(self) -> bool:
        return self.publisher is not None

    # -- this Zebra's own edges ----------------------------------------------------------------

    def _check_target(self, pubkey: str) -> str:
        pubkey = (pubkey or "").strip().lower()
        if not _KEY.match(pubkey):
            raise TrustRefused("that is not a Zebra public key")
        if pubkey == self.zebra_pubkey:
            raise TrustRefused("a Zebra cannot vouch for itself")
        return pubkey

    async def _set_own_edge(self, target: str, weight: float, reason: str) -> TrustEdge:
        old = await self.store.get_edge(self.zebra_pubkey, target)
        edge = TrustEdge(
            from_pubkey=self.zebra_pubkey,
            to_pubkey=target,
            weight=round(weight, 4),
            reason=reason,
            event_id=old.event_id if old else "",
            # strictly later than the last change, so a relay keeps the newest addressable event
            created_at=max(self.clock(), old.created_at + 1 if old else 0),
            relay_seq=None,
            published_weight=old.published_weight if old else None,
        )
        await self.store.save_edge(edge)
        return edge

    async def _publish(self, edge: TrustEdge) -> dict[str, Any] | None:
        """Sign and publish *edge*; None while publishing is off or when the relay failed
        (``publish_pending`` retries)."""
        if self.publisher is None:
            return None
        event = build_trust(
            edge.to_pubkey,
            edge.weight,
            edge.reason,
            device_secret=self.publisher.device_secret,
            zebra_pubkey=self.zebra_pubkey,
            chain=self.publisher.certs,
            created_at=max(self.clock(), edge.created_at),
        )
        try:
            result = await self.publisher.publish_event(event)
        except Exception as e:  # noqa: BLE001 - kept locally, retried next tick
            logger.warning("Commons: TRUST for %s… not published: %s", edge.to_pubkey[:12], e)
            return None
        await self.store.save_edge(
            replace(
                edge,
                event_id=event.id,
                created_at=event.created_at,
                relay_seq=result.get("receipt_seq"),
                published_weight=canonical_weight(edge.weight),
            )
        )
        logger.info("Commons: published TRUST %+.2f for %s…", edge.weight, edge.to_pubkey[:12])
        return result

    async def _owner_set(
        self,
        pubkey: str,
        *,
        weight: float,
        reason: str,
        vouched: bool,
        owner_weight: float | None,
        display_name: str | None,
    ) -> dict[str, Any]:
        target = self._check_target(pubkey)
        reason = clean_reason(reason)
        peer = await self.store.get_peer(target) or PeerRecord(pubkey=target)
        name = (display_name or "").strip()[:80] or peer.display_name
        await self.store.save_peer(
            replace(peer, display_name=name, vouched_by_user=vouched, owner_weight=owner_weight)
        )
        edge = await self._set_own_edge(target, weight, reason)
        result = await self._publish(edge)
        await self.recompute()
        return {
            "pubkey": target,
            "weight": edge.weight,
            "published": result is not None,
            "event_id": (result or {}).get("event_id"),
        }

    async def vouch(self, pubkey: str, *, display_name: str = "", note: str = "") -> dict[str, Any]:
        """The owner's "I know this Zebra": a seed, edge 0.8, published when publishing is on."""
        return await self._owner_set(
            pubkey,
            weight=VOUCH_WEIGHT,
            reason=note.strip() or VOUCHED,
            vouched=True,
            owner_weight=VOUCH_WEIGHT,
            display_name=display_name,
        )

    async def withdraw(self, pubkey: str, *, note: str = "") -> dict[str, Any]:
        """The owner withdraws a vouch or a distrust: edge 0, no longer a seed."""
        return await self._owner_set(
            pubkey,
            weight=0.0,
            reason=note.strip() or WITHDRAWN,
            vouched=False,
            owner_weight=None,
            display_name=None,
        )

    async def distrust(
        self, pubkey: str, *, note: str = "", weight: float = DISTRUST_WEIGHT
    ) -> dict[str, Any]:
        """The owner distrusts a Zebra: a negative edge that experience cannot raise."""
        if not -1.0 <= weight < 0:
            raise TrustRefused("distrust is a weight below 0")
        return await self._owner_set(
            pubkey,
            weight=weight,
            reason=note.strip() or DISTRUSTED,
            vouched=False,
            owner_weight=weight,
            display_name=None,
        )

    async def record_experience(self, publisher_pubkey: str, label: str) -> dict[str, Any] | None:
        """Move this Zebra's edge to *publisher_pubkey* after its own attestation *label*.

        Returns ``{weight, published}`` or None when the label says nothing about the publisher.
        """
        if not publisher_pubkey or publisher_pubkey == self.zebra_pubkey:
            return None
        old = await self.store.get_edge(self.zebra_pubkey, publisher_pubkey)
        peer = await self.store.touch_peer(publisher_pubkey)
        weight = experience_update(
            old.weight if old else None, label, owner_weight=peer.owner_weight
        )
        if weight is None:
            return None
        reason = old.reason if old and peer.owner_weight is not None else EXPERIENCE
        edge = await self._set_own_edge(publisher_pubkey, weight, reason)
        published = False
        if should_publish(edge.weight, edge.published_weight):
            published = await self._publish(edge) is not None
        await self.recompute()
        logger.info(
            "Commons: experience %s moved trust in %s… to %.2f",
            label,
            publisher_pubkey[:12],
            edge.weight,
        )
        return {"weight": edge.weight, "published": published}

    async def publish_pending(self) -> int:
        """Publish own edges whose change since the last published weight is meaningful."""
        if self.publisher is None:
            return 0
        sent = 0
        for edge in await self.store.list_edges():
            if edge.from_pubkey != self.zebra_pubkey:
                continue
            if edge.published_weight is None and edge.weight == 0:
                continue
            if edge.published_weight is not None and not should_publish(
                edge.weight, edge.published_weight
            ):
                continue
            if await self._publish(edge) is not None:
                sent += 1
        return sent

    # -- other Zebras' edges -------------------------------------------------------------------

    async def ingest(
        self, check: TrustVerification, event: Event, relay_seq: int | None = None
    ) -> bool:
        """Store a verified ``TRUST`` as an edge if it is the latest for its pair."""
        if not check.ok or check.from_pubkey is None or check.to_pubkey is None:
            return False
        own = check.from_pubkey == self.zebra_pubkey
        edge = TrustEdge(
            from_pubkey=check.from_pubkey,
            to_pubkey=check.to_pubkey,
            weight=float(check.weight or 0.0),
            reason=check.trust_reason or "",
            event_id=event.id,
            created_at=event.created_at,
            relay_seq=relay_seq,
            published_weight=float(check.weight or 0.0) if own else None,
        )
        if not own:
            await self.store.touch_peer(check.from_pubkey, event.created_at)
        if check.to_pubkey != self.zebra_pubkey:
            await self.store.touch_peer(check.to_pubkey)
        return await self.store.put_if_newer(edge)

    # -- local trust ---------------------------------------------------------------------------

    async def recompute(self) -> dict[str, float]:
        """Recompute every peer's local trust and best path; returns ``{pubkey: trust}``."""
        edges = await self.store.list_edges()
        peers = {p.pubkey: p for p in await self.store.list_peers()}
        seeds = {k for k, p in peers.items() if p.vouched_by_user}
        paths = compute_trust(
            self.zebra_pubkey, {(e.from_pubkey, e.to_pubkey): e.weight for e in edges}, seeds
        )
        for key in sorted(set(peers) | set(paths)):
            if key == self.zebra_pubkey:
                continue
            path = paths.get(key)
            value = path.value if path else 0.0
            best = path.to_dict() if path else {}
            peer = peers.get(key) or PeerRecord(pubkey=key)
            if key not in peers or peer.local_trust != value or peer.best_path != best:
                await self.store.save_peer(replace(peer, local_trust=value, best_path=best))
        return {k: p.value for k, p in paths.items()}

    async def trust_map(self) -> dict[str, float]:
        """``{pubkey: local trust}`` as last computed."""
        return {p.pubkey: p.local_trust for p in await self.store.list_peers()}

    async def score(self, publisher_pubkey: str, reports: Iterable[tuple[str, str]]) -> dict:
        """The import score of an offer by *publisher_pubkey* (``offer_score``)."""
        return offer_score(publisher_pubkey, reports, await self.trust_map(), self.zebra_pubkey)


def offer_score(
    publisher_pubkey: str,
    reports: Iterable[tuple[str, str]],
    trust: dict[str, float],
    zebra_pubkey: str | None,
) -> dict[str, Any]:
    """``{score, local_trust, signal, clears}`` for an offer.

    *reports* are ``(attesting Zebra, label)`` from verified ``ATTEST``s on its hash; this Zebra
    and the publisher never count.
    """
    local = trust.get(publisher_pubkey, 0.0)
    signal = attestation_signal(
        reports, trust, exclude={publisher_pubkey, *([zebra_pubkey] if zebra_pubkey else [])}
    )
    score = import_score(local, signal)
    return {
        "score": score,
        "local_trust": local,
        "signal": round(signal, 4),
        "clears": clears_threshold(score),
    }

"""Known Zebras and the trust edges between them (#233, S6).

``TrustStore`` is the interface; ``InMemoryTrustStore`` serves tests and the CLI, the web app's
``DjangoPeerTrustStore`` stores ``PeerModel`` and ``TrustEdgeModel`` rows. One edge is kept per
``(from_pubkey, to_pubkey)``: the latest (``is_newer``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class PeerRecord:
    """A Zebra this Zebra knows of.

    Attributes:
        pubkey: Its Zebra key (unique)
        display_name: A name the owner gave it ("" if none)
        vouched_by_user: The owner said "I know this Zebra"
        owner_weight: The weight the owner set (vouch 0.8, distrust < 0), None if none
        local_trust: Computed by ``trust.compute_trust``; 0 without a path from a vouched seed
        best_path: ``TrustPath.to_dict()`` of the best path
        last_seen: ``created_at`` of the newest event seen from it (0 if none)
    """

    pubkey: str
    display_name: str = ""
    vouched_by_user: bool = False
    owner_weight: float | None = None
    local_trust: float = 0.0
    best_path: dict[str, Any] = field(default_factory=dict)
    last_seen: int = 0


@dataclass(frozen=True)
class TrustEdge:
    """The latest edge ``from_pubkey → to_pubkey``.

    Attributes:
        weight: -1..1 (0: no trust either way)
        reason: A fixed reason or the owner's note
        event_id: The ``TRUST`` event it came from ("" while a local change is unpublished)
        created_at: That event's ``created_at`` (or the local change's time)
        relay_seq: The event's receipt ``seq``, if known
        published_weight: This Zebra's edges: the weight last published (None: never)
        pending: This Zebra's edges: an owner change not yet published; ``publish_pending``
            retries it whatever the experience threshold
    """

    from_pubkey: str
    to_pubkey: str
    weight: float
    reason: str
    event_id: str = ""
    created_at: int = 0
    relay_seq: int | None = None
    published_weight: float | None = None
    pending: bool = False


def is_newer(new: TrustEdge, old: TrustEdge | None) -> bool:
    """Whether *new* replaces *old*: receipt order when both have one, else ``created_at``.

    Ties (same time, no receipts) go to the higher event id, so every Zebra picks the same.
    """
    if old is None:
        return True
    if new.event_id and new.event_id == old.event_id:
        return False
    if new.relay_seq is not None and old.relay_seq is not None:
        return new.relay_seq > old.relay_seq
    if new.created_at != old.created_at:
        return new.created_at > old.created_at
    return new.event_id > old.event_id


class TrustStore(ABC):
    """Peers and trust edges."""

    @abstractmethod
    async def get_peer(self, pubkey: str) -> PeerRecord | None:
        """The peer with this key, or None."""

    @abstractmethod
    async def list_peers(self) -> list[PeerRecord]:
        """Every peer, highest local trust first (then by key)."""

    @abstractmethod
    async def save_peer(self, peer: PeerRecord) -> None:
        """Insert or replace the peer with ``peer.pubkey``."""

    @abstractmethod
    async def get_edge(self, from_pubkey: str, to_pubkey: str) -> TrustEdge | None:
        """The edge for this pair, or None."""

    @abstractmethod
    async def list_edges(self) -> list[TrustEdge]:
        """Every edge, ordered by (from, to)."""

    @abstractmethod
    async def save_edge(self, edge: TrustEdge) -> None:
        """Insert or replace the edge for ``(edge.from_pubkey, edge.to_pubkey)``."""

    # The three writers below touch only their own columns, so a writer holding an older copy of
    # the peer can never put back fields another writer changed meanwhile (#233 review).

    @abstractmethod
    async def touch_peer(self, pubkey: str, seen_at: int = 0) -> PeerRecord:
        """The peer, created if new, with ``last_seen`` raised to *seen_at* (nothing else)."""

    @abstractmethod
    async def set_owner_fields(
        self,
        pubkey: str,
        *,
        vouched_by_user: bool,
        owner_weight: float | None,
        display_name: str | None = None,
    ) -> None:
        """Write only the owner's columns (created if new); *display_name* None keeps it."""

    @abstractmethod
    async def set_computed(self, pubkey: str, local_trust: float, best_path: dict) -> None:
        """Write only ``local_trust`` and ``best_path`` (created if new)."""

    @abstractmethod
    async def mark_published(
        self,
        edge: TrustEdge,
        *,
        event_id: str,
        created_at: int,
        relay_seq: int | None,
        published_weight: float,
    ) -> bool:
        """Record that *edge* was published, only if the stored edge is still that change (same
        ``created_at``: every own change gets a later one); clears ``pending``. True if
        recorded."""

    async def put_if_newer(self, edge: TrustEdge) -> bool:
        """Store *edge* when it is newer than the stored one (``is_newer``); True if stored."""
        if not is_newer(edge, await self.get_edge(edge.from_pubkey, edge.to_pubkey)):
            return False
        await self.save_edge(edge)
        return True


class InMemoryTrustStore(TrustStore):
    """``TrustStore`` in dicts (tests, CLI)."""

    def __init__(self) -> None:
        self._peers: dict[str, PeerRecord] = {}
        self._edges: dict[tuple[str, str], TrustEdge] = {}

    async def get_peer(self, pubkey: str) -> PeerRecord | None:
        return self._peers.get(pubkey)

    async def list_peers(self) -> list[PeerRecord]:
        return sorted(self._peers.values(), key=lambda p: (-p.local_trust, p.pubkey))

    async def save_peer(self, peer: PeerRecord) -> None:
        self._peers[peer.pubkey] = peer

    async def get_edge(self, from_pubkey: str, to_pubkey: str) -> TrustEdge | None:
        return self._edges.get((from_pubkey, to_pubkey))

    async def list_edges(self) -> list[TrustEdge]:
        return [self._edges[k] for k in sorted(self._edges)]

    async def save_edge(self, edge: TrustEdge) -> None:
        self._edges[(edge.from_pubkey, edge.to_pubkey)] = edge

    # No await between read and write below: each is atomic in the event loop.

    async def touch_peer(self, pubkey: str, seen_at: int = 0) -> PeerRecord:
        peer = self._peers.get(pubkey) or PeerRecord(pubkey=pubkey)
        if pubkey not in self._peers or seen_at > peer.last_seen:
            peer = replace(peer, last_seen=max(seen_at, peer.last_seen))
            self._peers[pubkey] = peer
        return peer

    async def set_owner_fields(
        self,
        pubkey: str,
        *,
        vouched_by_user: bool,
        owner_weight: float | None,
        display_name: str | None = None,
    ) -> None:
        peer = self._peers.get(pubkey) or PeerRecord(pubkey=pubkey)
        self._peers[pubkey] = replace(
            peer,
            vouched_by_user=vouched_by_user,
            owner_weight=owner_weight,
            display_name=peer.display_name if display_name is None else display_name[:80],
        )

    async def set_computed(self, pubkey: str, local_trust: float, best_path: dict) -> None:
        peer = self._peers.get(pubkey) or PeerRecord(pubkey=pubkey)
        self._peers[pubkey] = replace(peer, local_trust=local_trust, best_path=dict(best_path))

    async def mark_published(
        self,
        edge: TrustEdge,
        *,
        event_id: str,
        created_at: int,
        relay_seq: int | None,
        published_weight: float,
    ) -> bool:
        key = (edge.from_pubkey, edge.to_pubkey)
        now = self._edges.get(key)
        if now is None or not _same_change(now, edge):
            return False
        self._edges[key] = replace(
            now,
            event_id=event_id,
            created_at=created_at,
            relay_seq=relay_seq,
            published_weight=published_weight,
            pending=False,
        )
        return True


def _same_change(a: TrustEdge, b: TrustEdge) -> bool:
    return a.created_at == b.created_at

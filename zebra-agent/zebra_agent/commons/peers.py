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
    """

    from_pubkey: str
    to_pubkey: str
    weight: float
    reason: str
    event_id: str = ""
    created_at: int = 0
    relay_seq: int | None = None
    published_weight: float | None = None


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

    async def touch_peer(self, pubkey: str, seen_at: int = 0) -> PeerRecord:
        """The peer, created if new, with ``last_seen`` raised to *seen_at*."""
        peer = await self.get_peer(pubkey)
        if peer is None or seen_at > peer.last_seen:
            peer = replace(peer or PeerRecord(pubkey=pubkey), last_seen=seen_at)
            await self.save_peer(peer)
        return peer

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

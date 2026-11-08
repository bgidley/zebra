"""``DjangoPeerTrustStore``: the web of trust in ``PeerModel`` / ``TrustEdgeModel`` (#233).

Rows carry ``user_id`` = the Commons owner (REQ-USR-002). ORM calls are
``sync_to_async(thread_sensitive=False)``: the exchange runs inside goal tasks and the daemon,
which outlive any request (#123).
"""

from __future__ import annotations

from asgiref.sync import sync_to_async
from zebra_agent.commons.peers import PeerRecord, TrustEdge, TrustStore

from zebra_agent_web.api.models import PeerModel, TrustEdgeModel


def _peer(row: PeerModel) -> PeerRecord:
    return PeerRecord(
        pubkey=row.pubkey,
        display_name=row.display_name,
        vouched_by_user=row.vouched_by_user,
        owner_weight=row.owner_weight,
        local_trust=row.local_trust,
        best_path=dict(row.best_path or {}),
        last_seen=row.last_seen,
    )


def _edge(row: TrustEdgeModel) -> TrustEdge:
    return TrustEdge(
        from_pubkey=row.from_pubkey,
        to_pubkey=row.to_pubkey,
        weight=row.weight,
        reason=row.reason,
        event_id=row.event_id,
        created_at=row.created_at,
        relay_seq=row.relay_seq,
        published_weight=row.published_weight,
    )


class DjangoPeerTrustStore(TrustStore):
    """``TrustStore`` over ``PeerModel`` and ``TrustEdgeModel``."""

    def __init__(self, owner_user_id: int | None):
        self.owner_user_id = owner_user_id

    @sync_to_async(thread_sensitive=False)
    def get_peer(self, pubkey: str) -> PeerRecord | None:
        row = PeerModel.objects.filter(pubkey=pubkey).first()
        return _peer(row) if row is not None else None

    @sync_to_async(thread_sensitive=False)
    def list_peers(self) -> list[PeerRecord]:
        return [_peer(r) for r in PeerModel.objects.order_by("-local_trust", "pubkey")]

    @sync_to_async(thread_sensitive=False)
    def save_peer(self, peer: PeerRecord) -> None:
        PeerModel.objects.update_or_create(
            pubkey=peer.pubkey,
            defaults={
                "display_name": peer.display_name[:80],
                "vouched_by_user": peer.vouched_by_user,
                "owner_weight": peer.owner_weight,
                "local_trust": peer.local_trust,
                "best_path": peer.best_path,
                "last_seen": peer.last_seen,
                "user_id": self.owner_user_id,
            },
        )

    @sync_to_async(thread_sensitive=False)
    def get_edge(self, from_pubkey: str, to_pubkey: str) -> TrustEdge | None:
        row = TrustEdgeModel.objects.filter(from_pubkey=from_pubkey, to_pubkey=to_pubkey).first()
        return _edge(row) if row is not None else None

    @sync_to_async(thread_sensitive=False)
    def list_edges(self) -> list[TrustEdge]:
        return [_edge(r) for r in TrustEdgeModel.objects.order_by("from_pubkey", "to_pubkey")]

    @sync_to_async(thread_sensitive=False)
    def save_edge(self, edge: TrustEdge) -> None:
        TrustEdgeModel.objects.update_or_create(
            from_pubkey=edge.from_pubkey,
            to_pubkey=edge.to_pubkey,
            defaults={
                "weight": edge.weight,
                "reason": edge.reason[:160],
                "event_id": edge.event_id,
                "created_at": edge.created_at,
                "relay_seq": edge.relay_seq,
                "published_weight": edge.published_weight,
                "user_id": self.owner_user_id,
            },
        )

"""The web of trust for this deployment (#233, S6). Off by default.

With publishing on, the engine's ``CommonsExchange`` carries the ``WebOfTrust`` (built in
``build_commons_exchange``): it fetches ``TRUST`` each daemon tick and publishes this Zebra's
own edges. With publishing off, ``get_web_of_trust`` returns a local-only one: the owner's
vouches are stored and local trust is computed, but nothing is published or fetched.

- ``vouch`` / ``withdraw`` / ``distrust``: the owner's actions on ``/commons/``.
- ``peers_overview``: what the ``/commons/`` peers section shows (database only).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from zebra_agent.commons import keys
from zebra_agent.commons.exchange import EXCHANGE_KEY, CommonsExchange
from zebra_agent.commons.identity import fingerprint
from zebra_agent.commons.trust import (
    EXPERIENCE,
    IMPORT_SCORE_THRESHOLD,
    REASONS,
    TrustPath,
    TrustRefused,
    path_text,
)
from zebra_agent.commons.web_of_trust import WebOfTrust

from zebra_agent_web.api.commons_identity import CommonsError, get_owner_id

logger = logging.getLogger(__name__)

__all__ = ["get_web_of_trust", "peers_overview", "parse_zebra_key", "IMPORT_SCORE_THRESHOLD"]


def parse_zebra_key(text: str) -> str:
    """A Zebra key from an ``npub`` or 64 hex characters; raises ``CommonsError``."""
    text = (text or "").strip()
    if text.startswith("npub1"):
        try:
            return keys.npub_decode(text)
        except ValueError as exc:
            raise CommonsError("That npub is not valid.") from exc
    if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
        return text.lower()
    raise CommonsError("Paste the other Zebra's npub (it starts with npub1).")


async def _zebra_pubkey() -> str | None:
    from zebra_agent_web.api.models import SystemStateModel

    state = await SystemStateModel.objects.filter(pk=1).afirst()
    return (state.zebra_pubkey if state else "") or None


async def get_web_of_trust() -> WebOfTrust:
    """The engine's (publishing on) or a local-only ``WebOfTrust``.

    Raises:
        CommonsError: This device has no Zebra yet.
    """
    from zebra_agent_web.api import agent_engine
    from zebra_agent_web.api import engine as engine_module
    from zebra_agent_web.commons_peer_store import DjangoPeerTrustStore

    await agent_engine.ensure_initialized()
    exchange = engine_module.get_engine().extras.get(EXCHANGE_KEY)
    if isinstance(exchange, CommonsExchange) and exchange.trust is not None:
        return exchange.trust
    zebra = await _zebra_pubkey()
    if not zebra:
        raise CommonsError("Start or join a Zebra first.")
    return WebOfTrust(DjangoPeerTrustStore(await get_owner_id()), zebra)


async def owner_action(action: str, key_text: str, *, display_name: str = "", note: str = ""):
    """Run the owner's *action* (``vouch`` / ``withdraw`` / ``distrust``); returns a message."""
    pubkey = parse_zebra_key(key_text)
    wot = await get_web_of_trust()
    try:
        if action == "vouch":
            result = await wot.vouch(pubkey, display_name=display_name, note=note)
            done = "I now count it as a Zebra you know"
        elif action == "withdraw":
            result = await wot.withdraw(pubkey, note=note)
            done = "I no longer count your word for it"
        elif action == "distrust":
            result = await wot.distrust(pubkey, note=note)
            done = "I will not trust it, whoever vouches for it"
        else:
            raise CommonsError("Unknown trust action.")
    except TrustRefused as exc:
        raise CommonsError(f"{str(exc).capitalize()}.") from exc
    logger.info("Owner trust action %s on %s…", action, pubkey[:12])
    tail = " and published it." if result["published"] else " (kept here: publishing is off)."
    return f"{done}{tail}"


def _label(pubkey: str, names: dict[str, str]) -> dict[str, str]:
    fp = fingerprint(pubkey)
    return {
        "pubkey": pubkey,
        "npub": keys.npub_encode(pubkey),
        "fingerprint": fp,
        "name": names.get(pubkey) or fp,
    }


def _voice(peer, own_edge, path: TrustPath) -> str:
    """Zebra's first-person line on why it trusts (or does not trust) a peer."""
    if peer.owner_weight is not None and peer.owner_weight < 0:
        return "You told me not to trust this Zebra, so I don't, whoever vouches for it."
    lines = []
    if peer.vouched_by_user:
        lines.append("You told me you know this Zebra, so I start from your word.")
    if own_edge is not None and own_edge.reason == EXPERIENCE:
        lines.append(f"My own runs of its workflows put my trust in it at {own_edge.weight:+.2f}.")
    if path.value > 0 and not peer.vouched_by_user:
        lines.append("I trust it through Zebras you know, along the path above.")
    elif path.value < 0:
        lines.append("A Zebra you know distrusts it, so I am wary of it.")
    elif path.value == 0:
        lines.append(
            "No Zebra you know vouches for it, so I give it no trust, whatever it publishes."
        )
    return " ".join(lines)


def _when(timestamp: int) -> datetime | None:
    return datetime.fromtimestamp(timestamp, UTC) if timestamp else None


async def peers_overview(zebra_pubkey: str | None, *, publishing_on: bool) -> dict[str, Any]:
    """The ``/commons/`` peers section; reads the database only (no relay)."""
    from zebra_agent_web.commons_peer_store import DjangoPeerTrustStore

    data: dict[str, Any] = {
        "publishing_on": publishing_on,
        "peers": [],
        "my_edges": [],
        "threshold": IMPORT_SCORE_THRESHOLD,
    }
    if not zebra_pubkey:
        return data
    store = DjangoPeerTrustStore(await get_owner_id())
    peers = await store.list_peers()
    edges = await store.list_edges()
    names = {p.pubkey: p.display_name for p in peers if p.display_name}
    names[zebra_pubkey] = "me"

    def name(pubkey: str) -> str:
        return _label(pubkey, names)["name"]

    def edge_row(e, other: str) -> dict[str, Any]:
        return {
            "zebra": _label(other, names),
            "weight": e.weight,
            "reason": e.reason,
            "fixed_reason": e.reason in REASONS,
            "published": bool(e.event_id) and e.published_weight is not None,
        }

    for peer in sorted(peers, key=lambda p: (not p.vouched_by_user, -p.local_trust, p.pubkey)):
        if peer.pubkey == zebra_pubkey:
            continue
        path = TrustPath.from_dict(peer.best_path)
        text = path_text(path, name)
        own = next(
            (e for e in edges if e.from_pubkey == zebra_pubkey and e.to_pubkey == peer.pubkey),
            None,
        )
        data["peers"].append(
            {
                "zebra": _label(peer.pubkey, names),
                "display_name": peer.display_name,
                "vouched": peer.vouched_by_user,
                "distrusted": peer.owner_weight is not None and peer.owner_weight < 0,
                "local_trust": peer.local_trust,
                "path_text": text,
                "has_path": bool(path.hops),
                "voice": _voice(peer, own, path),
                "last_seen": _when(peer.last_seen),
                "edges_out": [
                    edge_row(e, e.to_pubkey)
                    for e in edges
                    if e.from_pubkey == peer.pubkey and e.weight
                ],
                "edges_in": [
                    edge_row(e, e.from_pubkey)
                    for e in edges
                    if e.to_pubkey == peer.pubkey and e.weight
                ],
            }
        )
    data["my_edges"] = [
        edge_row(e, e.to_pubkey) for e in edges if e.from_pubkey == zebra_pubkey and e.weight
    ]
    return data

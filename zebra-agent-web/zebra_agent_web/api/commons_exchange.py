"""Offers in, attestations out, for this deployment (#232, S5). Off by default.

``build_commons_exchange`` returns a ``CommonsExchange`` only alongside a ``CommonsPublisher``
(``build_commons_publisher``: the Commons on, ``ZEBRA_COMMONS_RELAYS`` set, an identity and a
device key); ``agent_engine`` injects it as ``__commons_exchange__``. Without it nothing here
reaches a relay: the daemon's ``exchange_tick`` returns at once and no attestation is made.

- ``exchange_tick``: each daemon tick, ``poll()`` (new offers, revocations, attestations).
- ``start_offer_import``: the owner's "Import this" on ``/commons/``: the judged *Commons
  Import* on the mirrored ``OFFER``.
- ``offers_overview``: what the ``/commons/`` offers section shows.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from zebra_agent.commons import keys
from zebra_agent.commons.exchange import (
    EXCHANGE_KEY,
    CommonsExchange,
    attestation_summary,
    empty_summary,
    own_offers,
)
from zebra_agent.commons.identity import fingerprint
from zebra_agent.commons.kinds import ATTEST_KIND
from zebra_agent.commons.offers import IMPORTABLE, InvalidOfferTransition
from zebra_agent.commons.publisher import CommonsPublisher

from zebra_agent_web.api.commons_identity import CommonsError, get_owner_id

logger = logging.getLogger(__name__)

__all__ = [
    "EXCHANGE_KEY",
    "build_commons_exchange",
    "exchange_tick",
    "offers_overview",
    "start_offer_import",
]

_background: set[asyncio.Task] = set()


async def build_commons_exchange(publisher: CommonsPublisher | None) -> CommonsExchange | None:
    """The exchange over *publisher*, or None when there is no publisher (publishing off)."""
    if publisher is None:
        return None
    from zebra_agent_web.commons_offer_store import DjangoOfferStore

    return CommonsExchange(publisher=publisher, offers=DjangoOfferStore(await get_owner_id()))


async def exchange_tick(engine: object) -> None:
    """One daemon tick: read the Commons. Does nothing without an exchange; never raises."""
    exchange = getattr(engine, "extras", {}).get(EXCHANGE_KEY)
    if not isinstance(exchange, CommonsExchange):
        return
    try:
        counts = await exchange.poll()
    except Exception:  # noqa: BLE001 - never stops the daemon
        logger.exception("Commons: reading offers failed")
        return
    if any(counts.values()):
        logger.info("Commons: poll %s", counts)


async def start_offer_import(content_sha256: str, *, user_id: int | None) -> str:
    """Start *Commons Import* on the offer with this hash; returns the process id.

    The offer goes to ``judging``; the workflow runs in the background and parks on the
    owner's approval when a gate needs one. Its last step records the outcome and attests it.

    Raises:
        CommonsError: The Commons is stopped, publishing is off, or the offer is unknown or
            not importable now.
    """
    from zebra_tasks.launch import create_library_process

    from zebra_agent_web.api import agent_engine
    from zebra_agent_web.api import engine as engine_module
    from zebra_agent_web.api.commons_import import IMPORT_WORKFLOW, WebCommonsServices, _start

    reason = await WebCommonsServices().stop_reason()
    if reason:
        raise CommonsError(f"Imports are stopped: {reason}.")
    await agent_engine.ensure_initialized()
    engine = engine_module.get_engine()
    exchange = engine.extras.get(EXCHANGE_KEY)
    if not isinstance(exchange, CommonsExchange):
        raise CommonsError("Commons publishing is off (ZEBRA_COMMONS_RELAYS is not set).")
    try:
        offer_event = await exchange.begin_import(content_sha256)
    except KeyError as exc:
        raise CommonsError("I have not seen that offer.") from exc
    except InvalidOfferTransition as exc:
        raise CommonsError(f"{str(exc).capitalize()}.") from exc
    properties: dict[str, Any] = {
        "offer_event": offer_event,
        "goal": "Import a workflow offered on the Commons",
    }
    if user_id is not None:
        properties["__user_id__"] = user_id
    try:
        library = agent_engine.get_library()
        process = await create_library_process(
            engine,
            library.get_workflow(IMPORT_WORKFLOW),
            entry="direct_run",
            properties=properties,
        )
    except Exception:
        await exchange.abandon_import(content_sha256)
        raise
    task = asyncio.create_task(_start(engine, process.id))
    _background.add(task)
    task.add_done_callback(_background.discard)
    logger.info("Started Commons import %s of offer %s…", process.id, content_sha256[:12])
    return process.id


def _when(timestamp: int | None) -> datetime | None:
    return datetime.fromtimestamp(timestamp, UTC) if timestamp else None


def _zebra_label(pubkey: str) -> dict[str, str]:
    return {"pubkey": pubkey, "npub": keys.npub_encode(pubkey), "fingerprint": fingerprint(pubkey)}


async def offers_overview(zebra_pubkey: str | None, *, publishing_on: bool) -> dict[str, Any]:
    """The ``/commons/`` offers section: offers seen and this Zebra's own offers.

    Read from the local mirror and ``WorkflowOfferModel`` only: no relay is contacted here.
    """
    from zebra_agent_web.commons_mirror_store import DjangoCommonsMirror
    from zebra_agent_web.commons_offer_store import DjangoOfferStore

    owner = await get_owner_id()
    mirror = DjangoCommonsMirror(owner)
    attests = attestation_summary([m.event for m in await mirror.events(kind=ATTEST_KIND)])
    seen = []
    for record in await DjangoOfferStore(owner).list():
        judgement = record.judgement or {}
        seen.append(
            {
                "content_sha256": record.content_sha256,
                "short_hash": record.content_sha256[:12],
                "name": record.name,
                "summary": record.summary,
                "use_when": record.use_when,
                "stats": record.stats,
                "status": record.status,
                "publisher": _zebra_label(record.publisher_pubkey),
                "offered_at": record.offered_at,
                "offered_on": _when(record.offered_at),
                "attestations": attests.get(record.content_sha256, empty_summary()),
                "importable": record.status in IMPORTABLE,
                "voice": judgement.get("voice") or "",
                "recorded_reason": judgement.get("reason") or "",
                "process_id": judgement.get("process_id") or "",
            }
        )
    mine = await own_offers(mirror, zebra_pubkey) if zebra_pubkey else []
    for offer in mine:
        offer["short_hash"] = offer["content_sha256"][:12]
        offer["offered_on"] = _when(offer["offered_at"])
        for item in offer["attestations"]["items"]:
            item["zebra"] = _zebra_label(item["zebra_pubkey"])
            item["created_on"] = _when(item["created_at"])
    return {"publishing_on": publishing_on, "offers_seen": seen, "my_offers": mine}

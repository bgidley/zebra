"""Publishing offers to the public Commons for this deployment (#231, S4). Off by default.

``build_commons_publisher`` returns a ``CommonsPublisher`` only when the Commons is on
(``COMMONS_ENABLED``), ``COMMONS_RELAYS`` (``ZEBRA_COMMONS_RELAYS``) is set and this device has
a Zebra identity and device key; otherwise None, and the engine gets no
``__commons_publisher__``: exactly today's behaviour, no relay connection. Clients connect
lazily, so building the publisher opens nothing either.

``start_offer`` starts the *Commons Offer* workflow for one library workflow
(``manage.py commons_offer NAME``).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.conf import settings
from zebra_agent.commons.publisher import PUBLISHER_KEY, CommonsPublisher

from zebra_agent_web.api.commons_identity import (
    _chain_events,
    commons_enabled,
    get_commons_keys,
    get_owner_id,
)
from zebra_agent_web.api.models import SystemStateModel

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

OFFER_WORKFLOW = "Commons Offer"
__all__ = [
    "PUBLISHER_KEY",
    "build_commons_publisher",
    "commons_relays",
    "publish_tick",
    "start_offer",
]


def commons_relays() -> list[str]:
    """``COMMONS_RELAYS``: the public relay URLs, canonical first; [] when unset."""
    raw = str(settings.ZEBRA_AGENT_SETTINGS.get("COMMONS_RELAYS") or "")
    return list(dict.fromkeys(u for u in re.split(r"[\s,]+", raw.strip()) if u))


def commons_receipt_pubkey() -> str | None:
    """``COMMONS_RECEIPT_PUBKEY``: the canonical relay's operator key, or None."""
    value = str(settings.ZEBRA_AGENT_SETTINGS.get("COMMONS_RECEIPT_PUBKEY") or "")
    return value.strip().lower() or None


def publishing_configured() -> bool:
    """Whether publishing is switched on: the Commons is on and a relay is set."""
    return commons_enabled() and bool(commons_relays())


async def build_commons_publisher(library: WorkflowLibrary) -> CommonsPublisher | None:
    """This device's ``CommonsPublisher``, or None when publishing is off."""
    if not publishing_configured():
        return None
    try:
        state, _ = await SystemStateModel.objects.aget_or_create(pk=1)
        if not state.zebra_pubkey:
            logger.info("Commons: ZEBRA_COMMONS_RELAYS is set but this device has no Zebra yet")
            return None
        device_secret = await get_commons_keys().device_secret()
        if device_secret is None:
            logger.info("Commons: ZEBRA_COMMONS_RELAYS is set but there is no device key yet")
            return None
        # Imported here so nostr-sdk is never loaded while publishing is off.
        from zebra_agent.commons.nostr import NostrSdkTransport
        from zebra_agent.commons.relay import RelayCommonsClient

        from zebra_agent_web.commons_mirror_store import DjangoCommonsMirror

        canonical, *mirrors = [
            RelayCommonsClient(NostrSdkTransport(url, device_secret), private=False)
            for url in commons_relays()
        ]
        publisher = CommonsPublisher(
            canonical=canonical,
            mirrors=mirrors,
            device_secret=device_secret,
            zebra_pubkey=state.zebra_pubkey,
            mirror=DjangoCommonsMirror(await get_owner_id()),
            certs=await _chain_events(state.zebra_pubkey),
            sphere=state.sphere or "home",
            observed=state.sphere_observed,
            receipt_pubkey=commons_receipt_pubkey(),
        )
    except Exception:  # noqa: BLE001 - publishing never stops the app from starting
        logger.exception("Commons: could not build the publisher; publishing stays off")
        return None
    logger.info(
        "Commons publishing on: canonical %s, %d mirror(s), receipts %s",
        commons_relays()[0],
        len(mirrors),
        "verified" if publisher.receipt_pubkey else "off",
    )
    return publisher


async def publish_tick(engine: object) -> None:
    """One daemon tick: fetch receipts that arrived late. Does nothing without a publisher."""
    publisher = getattr(engine, "extras", {}).get(PUBLISHER_KEY)
    if not isinstance(publisher, CommonsPublisher):
        return
    try:
        found = await publisher.refresh_receipts()
        if found:
            logger.info("Commons: recorded %d late receipt(s)", found)
    except Exception:  # noqa: BLE001 - never stops the daemon
        logger.exception("Commons: receipt refresh failed")


async def start_offer(name: str, *, user_id: int | None) -> str:
    """Start *Commons Offer* for the library workflow *name* and run it until it finishes or
    parks on the owner's approval; returns the process id."""
    from zebra_tasks.launch import create_library_process

    from zebra_agent_web.api import agent_engine
    from zebra_agent_web.api import engine as engine_module

    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()
    engine = engine_module.get_engine()
    properties: dict = {"workflow_name": name, "goal": f"Offer {name} to the public Commons"}
    if user_id is not None:
        properties["__user_id__"] = user_id
    process = await create_library_process(
        engine, library.get_workflow(OFFER_WORKFLOW), entry="direct_run", properties=properties
    )
    await engine.start_process(process.id)
    return process.id

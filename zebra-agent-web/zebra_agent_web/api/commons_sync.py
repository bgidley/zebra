"""Skill sync over the private relay for this deployment (#246, S3b-2). Off by default.

``build_sync_service`` returns a ``SyncService`` over the real relay client only when the
Commons is on (``COMMONS_ENABLED``), ``SYNC_RELAY`` (``ZEBRA_SYNC_RELAY``) is set and this
device has a Zebra identity and device key; otherwise None, and the engine gets no
``__commons_sync__`` (exactly the behaviour before #246). ``sync_tick`` is the daemon's
per-tick step: reload certs from the database, resend queued events, pull this Zebra's certs
and revokes from the relay, publish identity and receive pending skills. Nothing here ever
raises into the caller.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from zebra_agent.commons.sync import (
    SYNC_DIRECTIONS,
    SyncService,
    can_receive,
    can_send,
    configured_direction,
)

from zebra_agent_web.api.commons_identity import (
    _chain_events,
    _state,
    commons_enabled,
    get_commons_keys,
)

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

SYNC_KEY = "__commons_sync__"


def sync_relay_url() -> str:
    """``SYNC_RELAY``: the private relay URL, or "" (no device sync)."""
    return str(settings.ZEBRA_AGENT_SETTINGS.get("SYNC_RELAY") or "").strip()


def sync_receipt_pubkey() -> str | None:
    """``SYNC_RECEIPT_PUBKEY``: the relay operator key trusted for receipts, or None."""
    value = str(settings.ZEBRA_AGENT_SETTINGS.get("SYNC_RECEIPT_PUBKEY") or "").strip().lower()
    return value or None


def sync_configured() -> bool:
    """Whether device sync is switched on: the Commons is on and a relay is set."""
    return commons_enabled() and bool(sync_relay_url())


def _direction(stored: str | None) -> str:
    """The stricter of ``ZEBRA_SYNC_DIRECTION`` and the direction stored for this device."""
    env = configured_direction()
    if stored not in SYNC_DIRECTIONS or stored == env:
        return env
    send = can_send(env) and can_send(stored)
    receive = can_receive(env) and can_receive(stored)
    return {(True, True): "both", (True, False): "send", (False, True): "receive"}.get(
        (send, receive), "off"
    )


def sync_status(stored_direction: str | None) -> dict:
    """What the `/commons/` page shows about skill sync on this device.

    Args:
        stored_direction: The direction stored for this device (`SystemStateModel`).

    Returns:
        ``on`` (Commons on and a relay set), ``relay`` URL, effective ``direction``
        and whether relay ``receipts`` are verified.
    """
    return {
        "on": sync_configured(),
        "relay": sync_relay_url(),
        "direction": _direction(stored_direction),
        "receipts": sync_receipt_pubkey() is not None,
    }


async def build_sync_service(library: WorkflowLibrary) -> SyncService | None:
    """This device's ``SyncService`` over the private relay, or None when sync is off."""
    if not sync_configured():
        return None
    try:
        state = await _state()
        if not state.zebra_pubkey:
            logger.info("Skill sync: ZEBRA_SYNC_RELAY is set but this device has no Zebra yet")
            return None
        device_secret = await get_commons_keys().device_secret()
        if device_secret is None:
            logger.info("Skill sync: ZEBRA_SYNC_RELAY is set but there is no device key yet")
            return None
        # Imported here so nostr-sdk is never loaded while sync is off.
        from zebra_agent.commons.nostr import NostrSdkTransport
        from zebra_agent.commons.relay import Outbox, RelayCommonsClient

        url = sync_relay_url()
        client = RelayCommonsClient(
            NostrSdkTransport(url, device_secret),
            outbox=Outbox(library.library_path / ".sync" / "outbox.jsonl"),
        )
        service = SyncService(
            client=client,
            device_secret=device_secret,
            zebra_pubkey=state.zebra_pubkey,
            sphere=state.sphere or "home",
            observed=state.sphere_observed,
            direction=_direction(state.sync_direction),
            certs=await _chain_events(state.zebra_pubkey),
            device_label=state.device_label,
            receipt_pubkey=sync_receipt_pubkey(),
        )
    except Exception:  # noqa: BLE001 - sync never stops the app from starting
        logger.exception("Skill sync: could not build the sync service; sync stays off")
        return None
    logger.info(
        "Skill sync on: relay %s, sphere %s, direction %s, receipts %s",
        url,
        service.sphere,
        service.direction,
        "verified" if service.receipt_pubkey else "off (S1 revocation rule)",
    )
    return service


async def sync_tick(engine: WorkflowEngine, library: WorkflowLibrary) -> None:
    """One daemon tick of skill sync; does nothing when the engine has no sync service."""
    sync = getattr(engine, "extras", {}).get(SYNC_KEY)
    if not isinstance(sync, SyncService):
        return
    steps = (
        ("certs", lambda: _reload_certs(sync)),
        ("flush", sync.flush),
        ("refresh", sync.refresh),
        ("identity", sync.publish_identity),
        ("receive", lambda: sync.receive_pending(engine, library)),
    )
    for name, step in steps:
        try:
            await step()
        except Exception:  # noqa: BLE001 - one failed step never stops the daemon
            logger.exception("Skill sync: %s step failed", name)


async def _reload_certs(sync: SyncService) -> None:
    """Pick up devices paired or revoked on this deployment since start."""
    sync.merge_certs(await _chain_events(sync.zebra_pubkey))

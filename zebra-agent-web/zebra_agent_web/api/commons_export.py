"""Signed single-workflow export and import for this deployment (Commons S2b, #229).

Glue between ``zebra_agent.commons.export`` (pure) and S1's keys and device table: the
export is signed with this device's key and carries its ``DEVICE_CERT`` chain; import
verifies against the certs and revokes this deployment holds and can adopt the
workflow into the library (``WorkflowLibrary.save(writer="adopt")``).

Used by ``manage.py commons_export`` / ``commons_import``. Both need ``COMMONS_ENABLED``.
"""

from __future__ import annotations

import logging
from typing import Any

from zebra_agent.commons import keys
from zebra_agent.commons.events import Event
from zebra_agent.commons.export import adopt_export, export_workflow, verify_export
from zebra_agent.commons.identity import fingerprint

from zebra_agent_web.api import agent_engine
from zebra_agent_web.api.commons_identity import (
    CommonsError,
    _chain_events,
    _ensure_device,
    _state,
    commons_enabled,
    get_commons_keys,
)
from zebra_agent_web.api.models import CommonsDeviceModel

logger = logging.getLogger(__name__)


def _require_enabled() -> None:
    if not commons_enabled():
        raise CommonsError("The Commons is off (COMMONS_ENABLED).")


async def export_workflow_file(name: str, *, with_golden: bool = False) -> str:
    """The signed export file text for workflow *name*.

    The file names this Zebra's display name; *with_golden* adds the workflow's golden
    tasks so an importer's gym can test it (#230).

    Raises:
        CommonsError: Commons off or no Zebra identity yet.
        zebra_agent.commons.export.ExportRefused: Not exportable or this device is not
            certified.
    """
    _require_enabled()
    state = await _state()
    if not state.zebra_pubkey:
        raise CommonsError("This deployment has no Zebra identity yet (see /commons/).")
    device_secret = await _ensure_device(state, get_commons_keys())
    chain = await _chain_events(state.zebra_pubkey)
    await agent_engine.ensure_initialized()
    text = await export_workflow(
        agent_engine.get_library(),
        name,
        device_secret=device_secret,
        zebra_pubkey=state.zebra_pubkey,
        chain=chain,
        display_name=state.zebra_display_name or None,
        with_golden=with_golden,
    )
    logger.info("Exported workflow %r signed by this device", name)
    return text


async def _held_events() -> list[Event]:
    """Every cert and revoke this deployment holds (revokes reject a signer)."""
    events: list[Event] = []
    async for row in CommonsDeviceModel.objects.all():
        events.append(Event.from_dict(row.cert_event))
        if row.revoke_event:
            events.append(Event.from_dict(row.revoke_event))
    return events


def _pubkey(value: str | None) -> str | None:
    """A hex pubkey from hex or ``npub1…``; None when empty."""
    if not value:
        return None
    value = value.strip()
    if value.startswith("npub1"):
        try:
            return keys.npub_decode(value)
        except ValueError as exc:
            raise CommonsError(f"invalid npub: {exc}") from exc
    return value.lower()


async def import_workflow_file(
    file_text: str,
    *,
    expected_zebra: str | None = None,
    adopt: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    """Verify an export file and, with *adopt*, adopt it into the library.

    The default local name is ``<name> (from <publisher fingerprint>)``.

    Returns:
        ``{ok, reason, zebra_pubkey, zebra_npub, name, content_sha256, adopted,
        adopted_name, path}``. Never raises for a file that does not verify.

    Raises:
        CommonsError: Commons off or an invalid ``expected_zebra``.
        zebra_agent.library.AdoptionRefused: The library refused the adoption.
    """
    _require_enabled()
    result = verify_export(
        file_text, expected_zebra=_pubkey(expected_zebra), revocations=await _held_events()
    )
    out: dict[str, Any] = {
        "ok": result.ok,
        "reason": result.reason,
        "zebra_pubkey": result.zebra_pubkey,
        "zebra_npub": keys.npub_encode(result.zebra_pubkey)
        if result.ok and result.zebra_pubkey
        else None,
        "name": result.name,
        "content_sha256": result.content_sha256,
        "adopted": False,
    }
    if not (result.ok and adopt):
        return out
    local_name = name or f"{result.name} (from {fingerprint(result.zebra_pubkey)})"
    await agent_engine.ensure_initialized()
    path = adopt_export(agent_engine.get_library(), result, name=local_name)
    out.update({"adopted": True, "adopted_name": local_name, "path": str(path)})
    logger.info("Adopted %r from Zebra %s", local_name, fingerprint(result.zebra_pubkey))
    return out

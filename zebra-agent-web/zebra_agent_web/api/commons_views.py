"""Web views for the Zebra Commons identity page (`/commons/`, #228).

GET shows the Zebra npub, the owner, this device and the device list. Every POST is
owner-only (403 otherwise) and returns 404 while ``COMMONS_ENABLED`` is off.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from functools import wraps
from urllib.parse import urlencode

from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from zebra_agent_web.api import commons_identity as ci
from zebra_agent_web.api.commons_sync import sync_status
from zebra_agent_web.api.identity import goal_identity

logger = logging.getLogger(__name__)


def _redirect(message: str = "", error: str = ""):
    params = {k: v for k, v in (("message", message), ("error", error)) if v}
    return redirect("/commons/" + (f"?{urlencode(params)}" if params else ""))


def _owner_action(view):
    """POST-only, Commons on, owner only."""

    @require_POST
    @wraps(view)
    async def wrapper(request, *args, **kwargs):
        if not ci.commons_enabled():
            raise Http404("Commons is off")
        user = await request.auser()
        if not await ci.is_owner(user):
            return HttpResponseForbidden("Only the Commons owner can do this.")
        try:
            return await view(request, *args, **kwargs)
        except ci.CommonsError as exc:
            return _redirect(error=str(exc))

    return wrapper


def _observed(request) -> bool:
    """'Who manages this device?' — anyone but me means the sphere is observed."""
    return request.POST.get("managed_by", "me") != "me"


def _sphere(request) -> str:
    sphere = request.POST.get("sphere", "").strip()
    if sphere == "other":
        sphere = request.POST.get("sphere_other", "").strip()
    return sphere


def _expiry(request) -> int | None:
    raw = request.POST.get("expires_on", "").strip()
    if not raw:
        return None
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ci.CommonsError("The expiry date is not valid.") from exc
    return int(day.timestamp())


async def _page(request, extra: dict | None = None, status: int = 200):
    from zebra_agent_web.api.commons_exchange import offers_overview
    from zebra_agent_web.api.commons_publish import publishing_configured
    from zebra_agent_web.api.commons_trust import peers_overview

    user = await request.auser()
    data = await ci.overview()
    offers: dict = {"publishing_on": False, "offers_seen": [], "my_offers": []}
    peers: dict = {"publishing_on": False, "peers": [], "my_edges": []}
    if data.get("enabled"):
        publishing_on = publishing_configured()
        offers = await offers_overview(data.get("zebra_pubkey"), publishing_on=publishing_on)
        peers = await peers_overview(data.get("zebra_pubkey"), publishing_on=publishing_on)
    context = {
        **await goal_identity(),
        **data,
        "commons_offers": offers,
        "commons_peers": peers,
        "sync": sync_status(data.get("sync_direction")),
        "is_owner": await ci.is_owner(user),
        "message": request.GET.get("message", ""),
        "error": request.GET.get("error", ""),
        "prefill_code": request.GET.get("code", ""),
        **(extra or {}),
    }
    response = render(request, "pages/commons.html", context, status=status)
    response["Cache-Control"] = "no-store"
    return response


async def commons_page(request):
    """The Commons identity page."""
    return await _page(request)


@_owner_action
async def commons_start(request):
    npub = await ci.start_zebra(
        display_name=request.POST.get("display_name", ""),
        label=request.POST.get("label", ""),
        sphere=_sphere(request),
        observed=_observed(request),
    )
    return _redirect(message=f"Your Zebra is {npub}")


@_owner_action
async def commons_pair(request):
    result = await ci.pair_device(
        code=request.POST.get("code", ""),
        label=request.POST.get("label", ""),
        sphere=_sphere(request),
        observed=_observed(request),
        expires_at=_expiry(request),
    )
    return await _page(
        request,
        {
            "cert_code": result["cert_code"],
            "paired_fingerprint": result["fingerprint"],
            "message": "Device certified. Paste the certificate code on that device.",
        },
    )


@_owner_action
async def commons_import(request):
    npub = await ci.import_cert(request.POST.get("cert_code", ""))
    return _redirect(message=f"This device now belongs to {npub}")


@_owner_action
async def commons_revoke(request, device_pubkey: str):
    await ci.revoke_device(device_pubkey, request.POST.get("reason", ""))
    return _redirect(message="Device revoked. Its signatures are no longer accepted.")


@_owner_action
async def commons_backup(request):
    nsec = await ci.export_backup()
    return await _page(request, {"backup_nsec": nsec})


@_owner_action
async def commons_restore(request):
    npub = await ci.restore_backup(request.POST.get("nsec", ""))
    return _redirect(message=f"Zebra key restored: {npub}")


@_owner_action
async def commons_workflow_import(request):
    """Start a judged import of an uploaded workflow file (#230); show its trace."""
    from zebra_agent_web.api.commons_import import MAX_IMPORT_BYTES, start_judged_import

    upload = request.FILES.get("export_file")
    if upload is None:
        raise ci.CommonsError("Choose a workflow export file.")
    if upload.size > MAX_IMPORT_BYTES:
        raise ci.CommonsError("The file is too large to be a workflow export.")
    try:
        text = upload.read().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ci.CommonsError("The file is not a workflow export (not UTF-8).") from exc
    user = await request.auser()
    process_id = await start_judged_import(text, user_id=user.id)
    return redirect(f"/processes/{process_id}/trace/")


@_owner_action
async def commons_offer_import(request, content_sha256: str):
    """The owner's "Import this" on an offer seen (#232): judged import; show its trace."""
    from zebra_agent_web.api.commons_exchange import start_offer_import

    user = await request.auser()
    process_id = await start_offer_import(content_sha256, user_id=user.id)
    return redirect(f"/processes/{process_id}/trace/")


@_owner_action
async def commons_clear_supervision(request, name: str):
    """The owner clears an adopted workflow's supervised flag (#230)."""
    from zebra_agent_web.api import agent_engine

    await agent_engine.ensure_initialized()
    if agent_engine.get_library().clear_supervision(name):
        logger.info("Owner cleared supervision of %r", name)
    return redirect("/workflows/")


@_owner_action
async def commons_trust(request):
    """The owner vouches for, withdraws from or distrusts a Zebra (#233). Never an LLM."""
    from zebra_agent_web.api.commons_trust import owner_action

    message = await owner_action(
        request.POST.get("action", ""),
        request.POST.get("zebra", ""),
        display_name=request.POST.get("display_name", ""),
        note=request.POST.get("note", ""),
    )
    return _redirect(message=message)


async def commons_genealogy(request):
    """The public genealogy (#247): public events in the mirror only. Empty while off."""
    from zebra_agent_web.api.public_genealogy_view import public_genealogy_context

    context = {"enabled": False}
    if ci.commons_enabled():
        context = await public_genealogy_context()
    response = render(request, "pages/commons_genealogy.html", context)
    response["Cache-Control"] = "no-store"
    return response


async def commons_genealogy_offer(request, content_sha256: str):
    """One public offer's family (#247); 404 unless it is an offer in the mirror."""
    from zebra_agent_web.api.public_genealogy_view import public_offer_context

    if not ci.commons_enabled():
        raise Http404("Commons is off")
    context = await public_offer_context(content_sha256)
    if context is None:
        raise Http404("No public offer with that hash")
    response = render(request, "pages/commons_genealogy_offer.html", context)
    response["Cache-Control"] = "no-store"
    return response

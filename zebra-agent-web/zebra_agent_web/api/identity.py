"""Single-user identity helpers — read and write the persisted identity.

Identity is stored in SystemStateModel (pk=1 singleton).  Both async and
sync variants are provided so they can be used from views and management
commands alike.

The ``user_identity_id`` is generated once on first call to
``set_identity`` and never changed — it is a stable local UUID.
"""

from __future__ import annotations

import uuid


def _to_dict(obj) -> dict:
    return {
        "display_name": obj.user_display_name,
        "identity_id": obj.user_identity_id,
        "setup_completed": obj.setup_completed,
    }


# ---------------------------------------------------------------------------
# Async variants
# ---------------------------------------------------------------------------


async def get_identity() -> dict:
    """Return current identity as a dict."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    return _to_dict(obj)


async def set_identity(display_name: str) -> dict:
    """Set the user display name, generate a stable UUID if needed, and mark setup complete."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    if not obj.user_identity_id:
        obj.user_identity_id = str(uuid.uuid4())
    obj.user_display_name = display_name.strip()
    obj.setup_completed = True
    await obj.asave()
    return _to_dict(obj)


async def is_setup_complete() -> bool:
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    return obj.setup_completed


# ---------------------------------------------------------------------------
# Sync variants (for middleware and management commands)
# ---------------------------------------------------------------------------


def get_identity_sync() -> dict:
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = SystemStateModel.objects.get_or_create(pk=1)
    return _to_dict(obj)


def set_identity_sync(display_name: str) -> dict:
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = SystemStateModel.objects.get_or_create(pk=1)
    if not obj.user_identity_id:
        obj.user_identity_id = str(uuid.uuid4())
    obj.user_display_name = display_name.strip()
    obj.setup_completed = True
    obj.save()
    return _to_dict(obj)


def is_setup_complete_sync() -> bool:
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = SystemStateModel.objects.get_or_create(pk=1)
    return obj.setup_completed


# ---------------------------------------------------------------------------
# Goal-process identity (``__user_display_name__`` / ``__user_identity_id__``)
# ---------------------------------------------------------------------------

_EMPTY_GOAL_IDENTITY = {"user_display_name": "", "user_identity_id": ""}


def _goal_identity(identity: dict) -> dict:
    return {
        "user_display_name": identity["display_name"],
        "user_identity_id": identity["identity_id"],
    }


def goal_identity_sync() -> dict:
    """Identity fields stamped onto goal processes, from a sync context.

    Returns ``{"user_display_name", "user_identity_id"}``; empty strings if the
    identity cannot be read (never raises).
    """
    try:
        return _goal_identity(get_identity_sync())
    except Exception:
        return dict(_EMPTY_GOAL_IDENTITY)


async def goal_identity() -> dict:
    """Async variant of :func:`goal_identity_sync` for async views and the CLI.

    The sync helper must not be called from a running event loop: Django
    raises ``SynchronousOnlyOperation`` and the identity would silently come
    back blank (#151).
    """
    try:
        return _goal_identity(await get_identity())
    except Exception:
        return dict(_EMPTY_GOAL_IDENTITY)

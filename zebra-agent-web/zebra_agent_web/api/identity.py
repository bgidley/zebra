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

"""Kill-switch helpers — read and write the persisted halted flag.

The flag is stored in SystemStateModel (pk=1 singleton). Both async and sync
variants are provided so they can be used from daemon coroutines and Django
management commands alike.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def is_halted() -> bool:
    """Return True if the kill switch is currently active."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    return obj.halted


async def set_halted(halted: bool, reason: str = "") -> dict:
    """Set the kill-switch state and return the updated status dict."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    obj.halted = halted
    obj.halted_at = _utcnow() if halted else None
    obj.halted_reason = reason if halted else ""
    await obj.asave()
    return _to_dict(obj)


async def get_status() -> dict:
    """Return the current kill-switch status as a serialisable dict."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    return _to_dict(obj)


def is_halted_sync() -> bool:
    """Synchronous variant for use in management commands."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = SystemStateModel.objects.get_or_create(pk=1)
    return obj.halted


def set_halted_sync(halted: bool, reason: str = "") -> dict:
    """Synchronous variant for use in management commands."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = SystemStateModel.objects.get_or_create(pk=1)
    obj.halted = halted
    obj.halted_at = _utcnow() if halted else None
    obj.halted_reason = reason if halted else ""
    obj.save()
    return _to_dict(obj)


def get_status_sync() -> dict:
    """Synchronous variant for use in management commands."""
    from zebra_agent_web.api.models import SystemStateModel

    obj, _ = SystemStateModel.objects.get_or_create(pk=1)
    return _to_dict(obj)


def _to_dict(obj) -> dict:
    return {
        "halted": obj.halted,
        "halted_at": obj.halted_at.isoformat() if obj.halted_at else None,
        "halted_reason": obj.halted_reason,
    }

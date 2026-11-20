"""Template context processors (settings only: no database access)."""

from __future__ import annotations

from zebra_agent_web.api.commons_identity import commons_enabled


def commons(request) -> dict:
    """``commons_enabled`` for the nav: the Commons link shows only when it is on (#228)."""
    return {"commons_enabled": commons_enabled()}


def onboarding(request) -> dict:
    """``onboarding_available``: the owner's Onboarding link shows only while the env allows it
    (``ZEBRA_ONBOARDING_ENABLED``, #276)."""
    from django.conf import settings

    return {
        "onboarding_available": bool(settings.ZEBRA_AGENT_SETTINGS.get("ONBOARDING_ENABLED", False))
    }

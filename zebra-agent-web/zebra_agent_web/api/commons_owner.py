"""The Commons owner and sphere, for the workflow library's provenance (#229).

S1 (#228) stores both on ``SystemStateModel`` (``commons_owner_user_id``,
``sphere``). Until those fields exist or are set, the owner is the routine owner
(first active superuser, else the first active user) and the sphere is ``local``.
"""

import logging

from zebra_agent.provenance import DEFAULT_SPHERE

logger = logging.getLogger(__name__)


async def resolve_commons_owner() -> tuple[int | None, str]:
    """Return ``(owner_user_id, sphere)``; the owner is None while no user exists."""
    from zebra_agent_web.api.daemon import resolve_routine_user
    from zebra_agent_web.api.models import SystemStateModel

    state = await SystemStateModel.objects.filter(pk=1).afirst()
    owner = getattr(state, "commons_owner_user_id", None) if state else None
    sphere = (getattr(state, "sphere", "") if state else "") or DEFAULT_SPHERE
    if owner is None:
        owner = await resolve_routine_user(None)
    return owner, sphere

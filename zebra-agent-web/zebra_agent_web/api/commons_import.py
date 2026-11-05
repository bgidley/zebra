"""Judged import and supervised use, web side (Commons S3, #230).

- ``WebCommonsServices``: the ``__commons__`` service in the engine's extras. Its
  ``stop_reason()`` stops Commons activity (imports, adoption, supervised launches)
  while ``COMMONS_ENABLED`` is off or the kill switch is on; ``held_events()`` gives
  the judge every cert and revoke this deployment holds.
- ``start_judged_import``: start the *Commons Import* workflow for an uploaded file.
- ``owner_only_refusal``: owner-only human tasks (``owner_only: true``) refuse anyone
  but the Commons owner.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from asgiref.sync import sync_to_async

from zebra_agent_web.api import agent_engine
from zebra_agent_web.api.commons_identity import CommonsError, commons_enabled, is_owner

logger = logging.getLogger(__name__)

IMPORT_WORKFLOW = "Commons Import"
#: Largest export file accepted (typical workflows are 2–20 KB).
MAX_IMPORT_BYTES = 256 * 1024

_background: set[asyncio.Task] = set()


class WebCommonsServices:
    """What the Commons task actions and the launch check need from the web app."""

    # Called from goal execution, which outlives the request that started it: ORM calls
    # must not be thread-sensitive (#123).

    async def stop_reason(self) -> str | None:
        """Why Commons activity is stopped, or None."""
        from zebra_agent_web.api.kill_switch import is_halted_sync

        if not commons_enabled():
            return "the Commons is off (COMMONS_ENABLED)"
        if await sync_to_async(is_halted_sync, thread_sensitive=False)():
            return "the kill switch is on"
        return None

    async def held_events(self) -> list:
        """Every cert and revoke this deployment holds."""
        return await sync_to_async(_held_events_sync, thread_sensitive=False)()


def _held_events_sync() -> list:
    from zebra_agent.commons.events import Event

    from zebra_agent_web.api.models import CommonsDeviceModel

    events = []
    for row in CommonsDeviceModel.objects.all():
        events.append(Event.from_dict(row.cert_event))
        if row.revoke_event:
            events.append(Event.from_dict(row.revoke_event))
    return events


def owner_only(task_def: Any) -> bool:
    """Whether a human task may only be completed by the Commons owner."""
    return bool((getattr(task_def, "properties", None) or {}).get("owner_only"))


async def owner_only_refusal(user: Any, task_def: Any) -> str | None:
    """The refusal message when *user* may not complete *task_def*, else None."""
    if owner_only(task_def) and not await is_owner(user):
        return "Only the Commons owner can answer this task."
    return None


async def start_judged_import(
    file_text: str,
    *,
    user_id: int | None,
    expected_zebra: str | None = None,
    wait: bool = False,
) -> str:
    """Start *Commons Import* for an export file; returns its process id.

    The workflow runs in the background unless *wait* (the CLI), so an upload returns
    at once; it parks on the owner's approval task when a gate needs one.

    Raises:
        CommonsError: The Commons is stopped, or the file is empty or too large.
    """
    from zebra_tasks.launch import create_library_process

    reason = await WebCommonsServices().stop_reason()
    if reason:
        raise CommonsError(f"Imports are stopped: {reason}.")
    if not file_text.strip():
        raise CommonsError("The file is empty.")
    if len(file_text.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise CommonsError("The file is too large to be a workflow export.")
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()
    from zebra_agent_web.api import engine as engine_module

    engine = engine_module.get_engine()
    properties: dict[str, Any] = {"export_file": file_text, "goal": "Import a workflow file"}
    if expected_zebra:
        properties["expected_zebra"] = expected_zebra
    if user_id is not None:
        properties["__user_id__"] = user_id
    process = await create_library_process(
        engine, library.get_workflow(IMPORT_WORKFLOW), entry="direct_run", properties=properties
    )
    if wait:
        await engine.start_process(process.id)
    else:
        task = asyncio.create_task(_start(engine, process.id))
        _background.add(task)
        task.add_done_callback(_background.discard)
    logger.info("Started Commons import %s", process.id)
    return process.id


async def _start(engine: Any, process_id: str) -> None:
    try:
        await engine.start_process(process_id)
    except Exception:
        logger.exception("Commons import %s failed to run", process_id)


async def resupervise_on_override() -> list[str]:
    """Emergency override: every adopted workflow asks before each run again (#230)."""
    try:
        await agent_engine.ensure_initialized()
        return agent_engine.get_library().resupervise_adopted()
    except Exception:  # the trust override itself must still succeed
        logger.exception("Emergency override could not re-supervise adopted workflows")
        return []

"""The one launch choke point for library workflows (#245, Commons S0).

Every start of a workflow loaded from the workflow library goes through
``create_library_process``: goals (``execute_goal_workflow``), the agent loop
(goal + dream cycle), direct runs, scheduled routines, ``subworkflow``,
``parallel_subworkflows`` and ``llm_agent`` tool calls. It calls ``check_launch``
before the process is created, so a refusal leaves nothing to clean up.

``check_launch`` enforces the Commons' supervised use (S3, #230): a library workflow
whose ``commons.supervised`` is set starts as a *Supervised run* wrapper that asks the
owner first (``zebra_tasks.commons.supervised``); while the Commons is stopped (off or
kill switch) such a launch is refused. See ``specs/zebra-commons-design.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from zebra.core.exceptions import ExecutionError

from zebra_tasks.commons.supervised import (
    SupervisedLaunch,
    commons_stop_reason,
    supervised_run_definition,
    supervision_for,
    workflow_actions,
    wrapper_properties,
)

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import ProcessDefinition, ProcessInstance

logger = logging.getLogger(__name__)

# The entry points that start library workflows, named so a check can tell them apart.
LAUNCH_ENTRIES = frozenset(
    {
        "goal",
        "agent_loop",
        "dream_cycle",
        "direct_run",
        "routine",
        "subworkflow",
        "parallel_subworkflows",
        "llm_agent_tool",
    }
)


class LaunchRefused(ExecutionError):
    """Raised by ``check_launch`` when a library workflow must not start."""


async def check_launch(
    definition: ProcessDefinition,
    *,
    entry: str,
    properties: dict[str, Any],
    extras: dict[str, Any] | None = None,
    registry: Any = None,
) -> SupervisedLaunch | None:
    """Decide whether *definition* may start from *entry*; raise ``LaunchRefused`` if not.

    Args:
        definition: The workflow about to be started.
        entry: Which entry point is starting it (one of ``LAUNCH_ENTRIES``).
        properties: The new process's initial properties.
        extras: The engine's extras (``__workflow_library__``, ``__commons__``).
        registry: The action registry, for the approval form's action hints.

    Returns:
        None to start it as is, or a ``SupervisedLaunch`` when the library marks it
        ``supervised`` (#230): it must then wait for the owner's pre-run approval.

    Raises:
        LaunchRefused: A supervised workflow while the Commons is stopped.
    """
    extras = extras or {}
    if not supervision_for(definition, extras):
        return None
    stopped = await commons_stop_reason(extras)
    if stopped:
        raise LaunchRefused(f"imported workflow {definition.name!r} is supervised and {stopped}")
    return SupervisedLaunch(definition.name, workflow_actions(definition, registry))


async def create_library_process(
    engine: WorkflowEngine,
    definition: ProcessDefinition,
    *,
    entry: str,
    properties: dict[str, Any] | None = None,
    parent_process_id: str | None = None,
    parent_task_id: str | None = None,
) -> ProcessInstance:
    """Create a process for a library workflow after ``check_launch`` allows it.

    The caller starts the returned process as before; this guards creation only.

    Args:
        engine: The workflow engine.
        definition: The library workflow to start.
        entry: Which entry point is starting it (one of ``LAUNCH_ENTRIES``).
        properties: Initial process properties.
        parent_process_id: Parent process, for child workflows.
        parent_task_id: Parent task, for child workflows.

    Returns:
        The created process, in CREATED state: a *Supervised run* wrapper that asks the
        owner first when ``check_launch`` says the workflow is supervised (#230).

    Raises:
        LaunchRefused: If ``check_launch`` refuses; no process is created.
        ValueError: If *entry* is not a known entry point.
    """
    if entry not in LAUNCH_ENTRIES:
        raise ValueError(f"Unknown launch entry {entry!r}")
    props = properties if properties is not None else {}
    try:
        launch = await check_launch(
            definition,
            entry=entry,
            properties=props,
            extras=getattr(engine, "extras", None),
            registry=getattr(engine, "actions", None),
        )
    except LaunchRefused as e:
        logger.warning("Launch of %r from %s refused: %s", definition.name, entry, e)
        raise
    parent: dict[str, str] = {}
    if parent_process_id is not None:
        parent["parent_process_id"] = parent_process_id
    if parent_task_id is not None:
        parent["parent_task_id"] = parent_task_id
    if isinstance(launch, SupervisedLaunch):
        # The real definition is started by the wrapper once the owner approves.
        await engine.store.save_definition(definition)
        logger.info("Launch of supervised %r from %s waits for approval", definition.name, entry)
        definition, props = (
            supervised_run_definition(definition),
            wrapper_properties(definition, launch, entry=entry, properties=props),
        )
    return await engine.create_process(definition, properties=props, **parent)

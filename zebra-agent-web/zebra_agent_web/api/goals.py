"""Shared goal-queueing logic used by both the web view and the zebra CLI.

Extracted from ``web_views.run_goal_queue`` so that goals queued from the
terminal and goals queued from the web form go through one code path and are
indistinguishable in stored properties.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra.core.models import ProcessInstance

logger = logging.getLogger(__name__)


async def queue_goal(
    goal: str,
    *,
    model: str | None = None,
    priority: int = 3,
    deadline: str | None = None,
    user_id: int | None = None,
    identity: dict | None = None,
    previous_run_context: dict | None = None,
    continuation_comment: str | None = None,
) -> ProcessInstance:
    """Queue a goal for budget-managed daemon execution.

    Creates an Agent Main Loop process in CREATED state with priority/deadline
    properties. The daemon will pick it up when budget allows.

    Args:
        goal: The goal text (must be non-empty).
        model: Model alias or full model name; resolved via resolve_model_name.
        priority: 1 (highest) to 5; clamped to that range.
        deadline: ISO datetime string, or None.
        user_id: Authenticated user id, or None.
        identity: Dict with user_display_name / user_identity_id (web supplies
            this from the request; the CLI omits it).
        previous_run_context: Summary of a previous run this goal follows up on
            (F116), or None.
        continuation_comment: User comment on where the previous run got to
            and what to do next (F134); only stored with previous_run_context.

    Returns:
        The created ProcessInstance (state CREATED).

    Raises:
        ValueError: If goal is empty or the Agent Main Loop workflow is missing.
    """
    from zebra_agent.library import list_goal_workflows
    from zebra_tasks.llm.models import resolve_model_name

    from zebra_agent_web.api import agent_engine, engine
    from zebra_agent_web.api.engine import get_engine

    goal = (goal or "").strip()
    if not goal:
        raise ValueError("Goal is required")

    resolved_model = resolve_model_name(model) if model else None
    priority = max(1, min(5, priority))

    await agent_engine.ensure_initialized()
    await engine.ensure_initialized()

    library = agent_engine.get_library()
    wf_engine = get_engine()

    definition = library.get_workflow("Agent Main Loop")

    available = await list_goal_workflows(library)

    identity = identity or {"user_display_name": "", "user_identity_id": ""}
    run_id = str(uuid.uuid4())
    properties = {
        "goal": goal,
        "run_id": run_id,
        "priority": priority,
        "available_workflows": available,
        "__llm_provider_name__": agent_engine.get_llm_provider_name(),
        "__llm_model__": resolved_model,
        "__started_at__": datetime.now(UTC).isoformat(),
        "__user_display_name__": identity.get("user_display_name", ""),
        "__user_identity_id__": identity.get("user_identity_id", ""),
        "__user_id__": user_id,
    }
    if deadline:
        properties["deadline"] = deadline
    if previous_run_context:
        properties["previous_run_context"] = previous_run_context
        if continuation_comment:
            properties["continuation_comment"] = continuation_comment

    process = await wf_engine.create_process(definition, properties=properties)
    logger.info(
        "Queued goal as process %s (priority=%d, deadline=%s)",
        process.id[:12],
        priority,
        deadline or "none",
    )
    return process

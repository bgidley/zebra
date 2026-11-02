"""Zebra Commons safety checks (#245, S0).

``commons_exportable`` is the one test of whether a workflow may ever leave this
deployment. Offering, exporting and syncing (S2, S3b, S4) call it; see
``specs/zebra-commons-design.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from zebra_tasks.agent.curator import is_protected_workflow

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowInfo


def commons_exportable(workflow: WorkflowInfo) -> bool:
    """Return whether *workflow* may be offered, exported or synced.

    Zebra's own workflows (tagged ``system`` or named in ``SYSTEM_WORKFLOW_NAMES``,
    e.g. the Agent Main Loop and the Dream Cycle) never leave: the optimizer can
    rewrite them, and an adopted copy would skip supervision. Nor do workflows
    whose lineage saw other users' runs (``commons.foreign_users``, #229), nor
    workflows with no ``commons`` block: written before #229, their lineage is
    unknown (the dream cycle may have learnt them from other users' runs), so they
    fail closed until a save gives them a block.

    Args:
        workflow: Library metadata with ``name``, ``tags`` and ``commons``.

    Returns:
        False if the workflow must stay on this deployment.
    """
    if is_protected_workflow(workflow):
        return False
    commons = getattr(workflow, "commons", None)
    if not isinstance(commons, dict):
        return False
    return commons.get("foreign_users") is False

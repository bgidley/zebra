"""Zebra Commons: identity, signed events and (later) workflow sharing over Nostr.

S0 (#245) provides ``commons_exportable``, the one test of whether a workflow may ever
leave this deployment. Offering, exporting and syncing (S2, S3b, S4) call it.

S1 (#228) provides the Zebra key, certified device keys, local ``DEVICE_CERT`` /
``DEVICE_REVOKE`` events and the cert-chain verify helper. Nothing here touches the
network or Django. See ``specs/zebra-commons-design.md``.
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
    rewrite them, and an adopted copy would skip supervision. S2a adds workflows
    whose lineage saw other users' runs (``foreign_users``).

    Args:
        workflow: Library metadata with ``name`` and ``tags``.

    Returns:
        False if the workflow must stay on this deployment.
    """
    return not is_protected_workflow(workflow)

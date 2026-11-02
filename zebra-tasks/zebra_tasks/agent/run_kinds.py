"""What kind of run a recorded ``WorkflowRun`` is: a goal, a tool call or a system run (#256).

A leaf module: ``llm_agent`` writes tool runs with ``TOOL_GOAL_PREFIX`` and the metrics
analysis reads them back, without either importing the other.
"""

from typing import Any

# Mirrors zebra_agent.library.SYSTEM_TAG; zebra-tasks does not import zebra-agent.
SYSTEM_TAG = "system"

#: Start of the goal of every tool run's ``WorkflowRun``: how metrics tell tool runs from goals.
TOOL_GOAL_PREFIX = "[tool] "

GOAL_RUN = "goal"
TOOL_RUN = "tool"
SYSTEM_RUN = "system"


def run_kind(run: dict[str, Any], system_workflows: set[str]) -> str:
    """Whether a run is a goal run, an ``llm_agent`` tool call or a system workflow's."""
    if str(run.get("goal") or "").startswith(TOOL_GOAL_PREFIX):
        return TOOL_RUN
    if run["workflow_name"] in system_workflows:
        return SYSTEM_RUN
    return GOAL_RUN

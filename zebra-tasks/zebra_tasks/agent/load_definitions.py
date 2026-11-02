"""LoadWorkflowDefinitionsAction - load workflow YAML via the WorkflowLibrary.

Uses the WorkflowLibrary from engine.extras to list and read workflow
definitions, ensuring compatibility with all storage backends.
"""

import logging
from typing import Any

import yaml
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

# Workflows that are internal to the agent and should not be evaluated
# or optimized by the dream cycle: these core ones, and every workflow tagged
# ``system`` (#251 — e.g. Improve Zebra, Outcome Review, Golden Gym).
SYSTEM_WORKFLOW_NAMES = frozenset(
    {
        "Agent Main Loop",
        "Dream Cycle",
        "Memory Compact Short",
        "Memory Compact Long",
    }
)
SYSTEM_TAG = "system"


def is_system_workflow(name: str, tags: list[str] | None) -> bool:
    """Whether a workflow is internal to Zebra, so the dream cycle must leave it alone."""
    return name in SYSTEM_WORKFLOW_NAMES or SYSTEM_TAG in (tags or [])


def is_system_workflow_name(library: Any, name: str) -> bool:
    """Whether *name* belongs to a system workflow in *library* (by name or its ``system`` tag).

    Used to stop the dream cycle writing a workflow that would shadow one (#251).
    """
    if name in SYSTEM_WORKFLOW_NAMES:
        return True
    if library is None:
        return False
    try:
        data = yaml.safe_load(library.get_workflow_yaml(name))
    except Exception:  # unknown name, unreadable file: not a system workflow we know of
        return False
    return isinstance(data, dict) and is_system_workflow(name, data.get("tags"))


class LoadWorkflowDefinitionsAction(TaskAction):
    """
    Load workflow definitions from the WorkflowLibrary.

    This action retrieves all (non-system) workflow YAML definitions via the
    ``WorkflowLibrary`` injected through ``context.extras["__workflow_library__"]``.

    It replaces the previous ``python_exec`` approach that read YAML files
    directly from disk, which broke when the library path wasn't a local
    filesystem (e.g. when using the Django-backed web app).

    Properties:
        exclude_system: Whether to skip system workflows (default: true)
        output_key: Where to store the definitions dict (default: "workflow_definitions")

    Output:
        Dict of ``{workflow_name: yaml_content_string}``

    Example workflow usage:
        ```yaml
        tasks:
          load_workflows:
            name: "Load Workflow Definitions"
            action: load_workflow_definitions
            auto: true
            properties:
              exclude_system: true
              output_key: workflow_definitions
        ```
    """

    # #245: effects stay in this run (reads, LLM calls, gates, audit appends)
    reversibility_hint = "always_reversible"

    description = "Load workflow definitions from the WorkflowLibrary."

    inputs = [
        ParameterDef(
            name="exclude_system",
            type="bool",
            description="Whether to exclude system/internal workflows",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the definitions dict",
            required=False,
            default="workflow_definitions",
        ),
    ]

    outputs = [
        ParameterDef(
            name="workflow_definitions",
            type="dict",
            description="Dict of workflow name -> YAML content",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Load workflow definitions from the library."""
        library = context.extras.get("__workflow_library__")
        if library is None:
            return TaskResult.fail(
                "No workflow library available. "
                "Ensure __workflow_library__ is set in engine.extras."
            )

        exclude_system = task.properties.get("exclude_system", True)
        output_key = task.properties.get("output_key", "workflow_definitions")

        try:
            workflows = await library.list_workflows()
            definitions: dict[str, str] = {}

            for wf in workflows:
                if exclude_system and is_system_workflow(wf.name, wf.tags):
                    continue

                try:
                    yaml_content = library.get_workflow_yaml(wf.name)
                    definitions[wf.name] = yaml_content
                except ValueError:
                    logger.warning(f"Could not load YAML for workflow '{wf.name}' — skipping")
                    continue

            logger.info(
                f"LoadWorkflowDefinitionsAction: loaded {len(definitions)} workflow definitions"
            )

            context.set_process_property(output_key, definitions)
            return TaskResult.ok(output=definitions)

        except Exception as e:
            return TaskResult.fail(f"Failed to load workflow definitions: {str(e)}")

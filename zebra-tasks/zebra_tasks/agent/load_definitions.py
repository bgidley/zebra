"""LoadWorkflowDefinitionsAction - load workflow YAML via the WorkflowLibrary.

Uses the WorkflowLibrary from engine.extras to list and read workflow
definitions, ensuring compatibility with all storage backends.
"""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

# Workflows that are internal to the agent and should not be evaluated
# or optimized by the dream cycle.
SYSTEM_WORKFLOW_NAMES = frozenset(
    {
        "Agent Main Loop",
        "Dream Cycle",
        "Memory Compact Short",
        "Memory Compact Long",
    }
)


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
                if exclude_system and wf.name in SYSTEM_WORKFLOW_NAMES:
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

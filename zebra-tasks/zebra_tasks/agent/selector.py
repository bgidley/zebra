"""Workflow selector action - uses LLM to select best workflow for a goal."""

import json
from dataclasses import dataclass
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider


@dataclass
class WorkflowInfo:
    """Metadata about a workflow for selection."""

    name: str
    description: str
    tags: list[str]
    success_rate: float  # 0.0 - 1.0
    use_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
        }


@dataclass
class WorkflowSelection:
    """Result of workflow selection."""

    workflow_name: str | None
    create_new: bool
    reasoning: str
    suggested_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowSelection":
        return cls(
            workflow_name=data.get("workflow_name"),
            create_new=data.get("create_new", False),
            reasoning=data.get("reasoning", ""),
            suggested_name=data.get("suggested_name"),
        )


class WorkflowSelectorAction(TaskAction):
    """
    Use LLM to select the best workflow for a given goal.

    Properties:
        goal: The user's goal/request
        available_workflows: List of WorkflowInfo dicts
        provider: LLM provider name (default: anthropic)
        model: LLM model name (optional)
        output_key: Where to store selection result (default: "selection")

    Output:
        WorkflowSelection with workflow_name, create_new flag, and reasoning

    Routes:
        - "create_new" - If a new workflow should be created
        - "use_existing" - If an existing workflow was selected

    Example workflow usage:
        ```yaml
        tasks:
          select_workflow:
            name: "Select Workflow"
            action: workflow_selector
            auto: true
            properties:
              goal: "{{goal}}"
              available_workflows: "{{available_workflows}}"
              output_key: selection

        routings:
          - from: select_workflow
            to: create_workflow
            condition: route_name
            name: "create_new"

          - from: select_workflow
            to: execute_workflow
            condition: route_name
            name: "use_existing"
        ```
    """

    description = "Use LLM to select the best workflow for a given goal."

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The user's goal/request",
            required=True,
        ),
        ParameterDef(
            name="available_workflows",
            type="list[dict]",
            description="List of workflow info dicts with name, description, tags, success_rate",
            required=False,
            default=[],
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider name",
            required=False,
            default="anthropic",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="LLM model name",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the selection result",
            required=False,
            default="selection",
        ),
    ]

    outputs = [
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Name of the selected workflow (null if creating new)",
            required=False,
        ),
        ParameterDef(
            name="create_new",
            type="bool",
            description="Whether a new workflow should be created",
            required=True,
        ),
        ParameterDef(
            name="reasoning",
            type="string",
            description="Explanation for the selection",
            required=True,
        ),
        ParameterDef(
            name="suggested_name",
            type="string",
            description="Suggested name for new workflow (if create_new is true)",
            required=False,
        ),
    ]

    SYSTEM_PROMPT = """You are a workflow selector. Given a user goal and available workflows,
select the best match or recommend creating a new one.

Consider:
- How well the workflow description matches the goal
- The workflow's success rate (higher is better)
- Whether the goal requires capabilities the workflow provides

Respond with JSON only:
{
    "workflow_name": "name of selected workflow" or null if creating new,
    "create_new": true if no good match exists,
    "reasoning": "brief explanation of your choice",
    "suggested_name": "name for new workflow" (only if create_new is true)
}"""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute workflow selection."""
        goal = task.properties.get("goal")
        if not goal:
            return TaskResult.fail("No goal provided")

        workflows = task.properties.get("available_workflows", [])

        # Get LLM provider
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            return TaskResult.fail(f"Failed to get LLM provider: {e}")

        # Build prompt
        prompt = f"Goal: {goal}\n\n"

        if workflows:
            prompt += "Available workflows:\n"
            for w in workflows:
                if isinstance(w, dict):
                    name = w.get("name", "Unknown")
                    desc = w.get("description", "No description")
                    rate = w.get("success_rate", 0.0)
                    tags = w.get("tags", [])
                else:
                    name = w.name
                    desc = w.description
                    rate = w.success_rate
                    tags = w.tags

                tags_str = ", ".join(tags) if tags else "none"
                prompt += f"- {name}: {desc} (success: {rate:.0%}, tags: {tags_str})\n"
        else:
            prompt += "No workflows available yet. You must create a new one.\n"

        try:
            response = await provider.complete(
                messages=[
                    Message.system(self.SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.3,  # Lower temperature for more consistent selection
                max_tokens=500,
            )

            # Parse JSON response
            content = response.content or ""

            # Extract JSON from potential code blocks
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                content = content[start:end].strip()

            selection_data = json.loads(content)
            selection = WorkflowSelection.from_dict(selection_data)

            # If no workflows available, force create_new
            if not workflows and not selection.create_new:
                selection.create_new = True
                selection.workflow_name = None

            # Determine next route for conditional routing
            next_route = "create_new" if selection.create_new else "use_existing"

            # Store workflow name in process properties for later use
            if selection.workflow_name:
                context.set_process_property("workflow_name", selection.workflow_name)

            # Store selection in output_key
            output_key = task.properties.get("output_key", "selection")
            output_data = {
                "workflow_name": selection.workflow_name,
                "create_new": selection.create_new,
                "reasoning": selection.reasoning,
                "suggested_name": selection.suggested_name,
            }
            context.set_process_property(output_key, output_data)

            return TaskResult(
                success=True,
                output=output_data,
                next_route=next_route,
            )

        except json.JSONDecodeError as e:
            return TaskResult.fail(f"Failed to parse LLM response as JSON: {e}")
        except Exception as e:
            return TaskResult.fail(f"Workflow selection failed: {e}")

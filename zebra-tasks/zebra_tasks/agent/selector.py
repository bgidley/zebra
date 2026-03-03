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
    create_variant: bool
    reasoning: str
    suggested_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowSelection":
        return cls(
            workflow_name=data.get("workflow_name"),
            create_new=data.get("create_new", False),
            create_variant=data.get("create_variant", False),
            reasoning=data.get("reasoning", ""),
            suggested_name=data.get("suggested_name"),
        )


class WorkflowSelectorAction(TaskAction):
    """
    Use LLM to select the best workflow for a given goal.

    Receives optional conceptual memory context and a pre-computed shortlist
    from the consult_memory step. Uses these to make a richer decision:
    use an existing workflow, create a variant of one, or create a new one.

    Properties:
        goal: The user's goal/request
        available_workflows: List of WorkflowInfo dicts
        memory_context: Conceptual memory context string (optional)
        shortlist: List of workflow names from memory (optional)
        provider: LLM provider name (default: anthropic)
        model: LLM model name (optional)
        output_key: Where to store selection result (default: "selection")

    Output:
        WorkflowSelection with workflow_name, create_new, create_variant flags,
        reasoning, and suggested_name.

    Routes:
        - "create_new"     — No existing workflow fits; create from scratch
        - "create_variant" — An existing workflow almost fits; copy and modify
        - "use_existing"   — Use an existing workflow directly

    Example workflow usage:
        ```yaml
        tasks:
          select_workflow:
            name: "Select Workflow for Goal"
            action: workflow_selector
            auto: true
            properties:
              goal: "{{goal}}"
              available_workflows: "{{available_workflows}}"
              memory_context: "{{memory_shortlist.memory_context}}"
              shortlist: "{{memory_shortlist.shortlist}}"
              output_key: selection

        routings:
          - from: select_workflow
            to: create_workflow
            condition: route_name
            name: "create_new"

          - from: select_workflow
            to: create_variant
            condition: route_name
            name: "create_variant"

          - from: select_workflow
            to: execute_workflow
            condition: route_name
            name: "use_existing"
        ```
    """

    _logger = None

    @classmethod
    def _get_logger(cls):
        if cls._logger is None:
            import logging

            cls._logger = logging.getLogger(__name__)
        return cls._logger

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
            name="memory_context",
            type="string",
            description="Conceptual memory context string from consult_memory step",
            required=False,
            default="",
        ),
        ParameterDef(
            name="shortlist",
            type="list",
            description="Workflow names pre-recommended by conceptual memory",
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
            description="Whether a brand-new workflow should be created",
            required=True,
        ),
        ParameterDef(
            name="create_variant",
            type="bool",
            description="Whether a variant of an existing workflow should be created",
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
            description="Suggested name for new/variant workflow",
            required=False,
        ),
    ]

    SYSTEM_PROMPT = """You are a workflow selector. Given a user goal and available workflows,
select the best action: use an existing workflow, create a variant of one, or create a new one.

WORKFLOW CAPABILITIES:
The engine supports these patterns — an existing workflow may already handle the goal:
- Sequential steps (one task after another)
- Parallel execution (multiple tasks at once, synchronized join)
- Conditional branching (exclusive choice based on data or decisions)
- Loops (repeat steps until a condition is met)
- Human tasks (auto: false) — pause for user input via web forms
- Deferred choice (parallel human tasks — first completed wins)

SELECTION RULES:
1. ALWAYS prefer an existing workflow if it can handle the goal — bias strongly toward use_existing
2. create_variant is for structural changes only: different number of tasks, different human
   interaction pattern, or a fundamentally different sequence of steps. NOT for topic differences.
   A general brainstorm/question workflow can handle any topic — topic alone is NOT a reason to
   create a variant.
3. Only use create_new if no existing workflow structure is even close
4. Pay close attention to "use_when" — it describes when to use each workflow
5. The memory context (if present) contains past experience — prioritise it

DECISION MATRIX:
- Good fit → use_existing (workflow_name = selected workflow)
- Same structure needed but different steps → create_variant (workflow_name = source to copy)
- No fit at all → create_new (workflow_name = null)

EXAMPLES of when NOT to create a variant:
- "Select a bike for a 10-year-old" → use_existing "Brainstorm Ideas" (same pattern, just different topic)
- "What is the capital of France?" → use_existing "Answer Question" (same pattern)
- Any factual/creative/reasoning goal → use an existing general-purpose workflow

NAMING (for create_new / create_variant):
- Use Title Case with spaces (e.g. "Code Review Strict", "Bug Triage Fast")
- Be specific and descriptive
- 2-4 words that capture the workflow's purpose

Respond with JSON only:
{
    "workflow_name": "name of selected or source workflow" or null if create_new,
    "create_new": true ONLY if no existing workflow is even close,
    "create_variant": true ONLY if an existing workflow is close but needs modification,
    "reasoning": "brief explanation of your choice",
    "suggested_name": "name for new/variant workflow" (only if create_new or create_variant)
}

Note: create_new and create_variant are mutually exclusive. If use_existing, both are false."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute workflow selection."""
        goal = task.properties.get("goal")
        if not goal:
            return TaskResult.fail("No goal provided")

        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        workflows = task.properties.get("available_workflows", [])
        if isinstance(workflows, str) and "{{" in workflows:
            workflows = context.resolve_template(workflows)
        if isinstance(workflows, str):
            try:
                workflows = json.loads(workflows)
            except json.JSONDecodeError:
                import ast

                try:
                    workflows = ast.literal_eval(workflows)
                except (ValueError, SyntaxError):
                    workflows = []

        # Memory context and shortlist from consult_memory step
        memory_context = task.properties.get("memory_context", "")
        if isinstance(memory_context, str) and "{{" in memory_context:
            memory_context = context.resolve_template(memory_context)

        shortlist = task.properties.get("shortlist", [])
        if isinstance(shortlist, str) and "{{" in shortlist:
            shortlist = context.resolve_template(shortlist)
        if isinstance(shortlist, str):
            try:
                shortlist = json.loads(shortlist)
            except (json.JSONDecodeError, ValueError):
                shortlist = []

        # Get LLM provider
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")

        callback = context.extras.get("__progress_callback__")
        if callback:
            await callback("selecting_workflow", {"available_count": len(workflows)})

        logger = self._get_logger()
        logger.info(f"Selecting workflow for goal: {goal[:100]}...")
        logger.info(f"Available workflows: {len(workflows)}, shortlist: {len(shortlist)}")

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            return TaskResult.fail(f"Failed to get LLM provider: {e}")

        # Build prompt
        prompt = f"Goal: {goal}\n\n"

        # Inject memory context if available
        if memory_context:
            prompt += f"{memory_context}\n\n"

        # Highlight shortlisted workflows
        if shortlist:
            prompt += (
                f"Memory-recommended workflows (strong candidates): {', '.join(shortlist)}\n\n"
            )

        if workflows:
            prompt += "Available workflows:\n"
            for w in workflows:
                if isinstance(w, dict):
                    name = w.get("name", "Unknown")
                    desc = w.get("description", "No description")
                    rate = w.get("success_rate", 0.0)
                    tags = w.get("tags", [])
                    use_when = w.get("use_when", "")
                else:
                    name = w.name
                    desc = w.description
                    rate = w.success_rate
                    tags = w.tags
                    use_when = getattr(w, "use_when", "")

                # Mark shortlisted workflows
                marker = " [MEMORY RECOMMENDED]" if name in shortlist else ""
                tags_str = ", ".join(tags) if tags else "none"
                prompt += f"- {name}{marker}: {desc}\n"
                if use_when:
                    prompt += f"  USE WHEN: {use_when}\n"
                prompt += f"  (success: {rate:.0%}, tags: {tags_str})\n"
        else:
            prompt += "No workflows available yet. You must create a new one.\n"

        try:
            response = await provider.complete(
                messages=[
                    Message.system(self.SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.3,
                max_tokens=500,
            )

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

            logger.info(
                f"LLM selection: workflow={selection.workflow_name}, "
                f"create_new={selection.create_new}, create_variant={selection.create_variant}"
            )
            logger.info(f"LLM reasoning: {selection.reasoning[:150]}...")

            # If no workflows available, force create_new
            if not workflows and not selection.create_new:
                selection.create_new = True
                selection.create_variant = False
                selection.workflow_name = None

            # Ensure mutual exclusion
            if selection.create_new and selection.create_variant:
                selection.create_variant = False

            # Determine next route
            if selection.create_new:
                next_route = "create_new"
            elif selection.create_variant:
                next_route = "create_variant"
            else:
                next_route = "use_existing"

            if callback:
                await callback(
                    "workflow_selected",
                    {
                        "workflow_name": selection.workflow_name,
                        "reasoning": selection.reasoning,
                        "created_new": False,
                    },
                )

            # Store workflow name in process properties for later use.
            # For use_existing: this is the name to execute directly.
            # For create_variant: this is the source workflow name (variant_creator
            # will overwrite it with the new variant name once created).
            if selection.workflow_name:
                context.set_process_property("workflow_name", selection.workflow_name)

            output_key = task.properties.get("output_key", "selection")
            output_data = {
                "workflow_name": selection.workflow_name,
                "create_new": selection.create_new,
                "create_variant": selection.create_variant,
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

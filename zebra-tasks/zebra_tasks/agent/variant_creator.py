"""WorkflowVariantCreatorAction - LLM-driven copy-and-modify of an existing workflow."""

import re

from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider


class WorkflowVariantCreatorAction(TaskAction):
    """
    Create a new workflow by copying and modifying an existing one.

    The LLM receives the source workflow YAML plus the goal that doesn't quite fit,
    and produces a modified copy that addresses the gap. The original workflow is
    left unchanged; the variant is saved with a new name.

    Properties:
        goal: The user's goal that the source workflow almost fits
        source_workflow_name: Name of the workflow to copy and modify
        suggested_name: Suggested name for the variant (optional)
        reasoning: Why the source workflow was chosen (provides context to LLM)
        provider: LLM provider name (default: anthropic)
        model: LLM model name (optional)
        output_key: Where to store the result (default: "created_workflow")

    Output:
        - yaml: Generated variant YAML string
        - name: Workflow name
        - definition_id: Definition ID
        - source_workflow_name: Name of the original workflow

    Routes:
        No route — continues to execute_workflow like create_workflow does.

    Example workflow usage:
        ```yaml
        tasks:
          create_variant:
            name: "Create Workflow Variant"
            action: workflow_variant_creator
            auto: true
            properties:
              goal: "{{goal}}"
              source_workflow_name: "{{selection.workflow_name}}"
              suggested_name: "{{selection.suggested_name}}"
              reasoning: "{{selection.reasoning}}"
              output_key: created_workflow
        ```
    """

    description = "Create a workflow variant by LLM-copying and modifying an existing workflow."

    inputs = [
        ParameterDef(name="goal", type="string", description="User's goal", required=True),
        ParameterDef(
            name="source_workflow_name",
            type="string",
            description="Name of the workflow to base the variant on",
            required=True,
        ),
        ParameterDef(
            name="suggested_name",
            type="string",
            description="Suggested name for the new variant",
            required=False,
        ),
        ParameterDef(
            name="reasoning",
            type="string",
            description="Why the source workflow was close but not quite right",
            required=False,
            default="",
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider",
            required=False,
            default="anthropic",
        ),
        ParameterDef(name="model", type="string", description="LLM model", required=False),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="created_workflow",
        ),
    ]

    outputs = [
        ParameterDef(
            name="yaml", type="string", description="Generated variant YAML", required=True
        ),
        ParameterDef(name="name", type="string", description="Workflow name", required=True),
        ParameterDef(
            name="definition_id", type="string", description="Definition ID", required=True
        ),
        ParameterDef(
            name="source_workflow_name",
            type="string",
            description="Source workflow that was varied",
            required=True,
        ),
    ]

    SYSTEM_PROMPT = (
        "You are a workflow designer for the Zebra workflow engine.\n"
        "You are given an existing workflow YAML and a new goal that is similar but not\n"
        "identical. Your job is to produce a modified copy of the workflow (a 'variant')\n"
        "that serves the new goal.\n"
        "\n"
        "Rules:\n"
        "1. Keep the overall structure similar — change only what is needed\n"
        "2. Update the `name` field to a descriptive new name\n"
        "   (e.g. 'Code Review Strict')\n"
        "3. Update `description` and `use_when` to reflect the variant's purpose\n"
        "4. Modify tasks, prompts, and properties as needed for the new goal\n"
        "5. Do NOT copy the source workflow name — always give the variant a distinct name\n"
        "6. Return ONLY valid YAML — no explanations, no markdown code blocks\n"
        "7. Set `result_key` to the output_key of the final task that produces the main\n"
        "   human-readable result. If the source has a result_key, update it as needed.\n"
        "   The result_key value is what the UI shows as the workflow output.\n"
        "\n"
        "The available task actions are the same as in the source workflow."
    )

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute variant creation."""
        goal = self._resolve(task, context, "goal", "")
        source_name = self._resolve(task, context, "source_workflow_name", "")
        suggested_name = self._resolve(task, context, "suggested_name", "")
        reasoning = self._resolve(task, context, "reasoning", "")
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")
        output_key = task.properties.get("output_key", "created_workflow")

        if not goal:
            return TaskResult.fail("No goal provided")
        if not source_name:
            return TaskResult.fail("No source_workflow_name provided")

        # Load source YAML from library
        library = context.extras.get("__workflow_library__")
        if library is None:
            return TaskResult.fail("No workflow library available")

        try:
            source_yaml = library.get_workflow_yaml(source_name)
        except Exception as e:
            return TaskResult.fail(f"Could not load source workflow '{source_name}': {e}")

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            return TaskResult.fail(f"Failed to get LLM provider: {e}")

        # Emit progress event
        callback = context.extras.get("__progress_callback__")
        if callback:
            await callback(
                "creating_variant", {"source": source_name, "suggested_name": suggested_name}
            )

        prompt = f"New goal: {goal}\n"
        if suggested_name:
            prompt += f"Suggested variant name: {suggested_name}\n"
        if reasoning:
            prompt += f"Why the source doesn't quite fit: {reasoning}\n"
        prompt += f"\nSource workflow YAML:\n{source_yaml}"

        try:
            response = await provider.complete(
                messages=[
                    Message.system(self.SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.5,
                max_tokens=2500,
            )

            yaml_content = self._extract_yaml(response.content or "")

            try:
                definition = load_definition_from_yaml(yaml_content)
            except Exception as e:
                return TaskResult.fail(f"Generated invalid variant YAML: {e}")

            # Save to library
            if library is not None:
                try:
                    library.add_workflow(yaml_content)
                except Exception:
                    pass  # Don't fail — workflow is still valid

            if callback:
                await callback(
                    "workflow_selected",
                    {
                        "workflow_name": definition.name,
                        "reasoning": f"Created variant of '{source_name}': {definition.name}",
                        "created_new": True,
                    },
                )

            output_data = {
                "yaml": yaml_content,
                "name": definition.name,
                "definition_id": definition.id,
                "source_workflow_name": source_name,
            }
            context.set_process_property(output_key, output_data)
            context.set_process_property("workflow_name", definition.name)
            context.set_process_property("created_new", True)

            return TaskResult.ok(output=output_data)

        except Exception as e:
            return TaskResult.fail(f"Variant creation failed: {e}")

    def _resolve(
        self, task: TaskInstance, context: ExecutionContext, key: str, default: str
    ) -> str:
        value = task.properties.get(key, default)
        if isinstance(value, str) and "{{" in value:
            value = context.resolve_template(value)
        return value or default

    def _extract_yaml(self, content: str) -> str:
        """Strip markdown code blocks if present."""
        patterns = [
            r"```yaml\s*(.*?)\s*```",
            r"```yml\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
        return content.strip()

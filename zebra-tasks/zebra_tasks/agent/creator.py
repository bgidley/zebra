"""Workflow creator action - uses LLM to create new workflow definitions."""

import json
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider


class WorkflowCreatorAction(TaskAction):
    """
    Use LLM to create a new workflow definition in YAML format.

    Properties:
        goal: The user's goal that the workflow should achieve
        suggested_name: Suggested name for the workflow (optional)
        existing_workflows: List of existing workflow summaries for reference (optional)
        provider: LLM provider name (default: anthropic)
        model: LLM model name (optional)

    Output:
        Dictionary with 'yaml' (string) and 'name' (string)
    """

    description = "Use LLM to create a new workflow definition in YAML format."

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The user's goal that the workflow should achieve",
            required=True,
        ),
        ParameterDef(
            name="suggested_name",
            type="string",
            description="Suggested name for the workflow",
            required=False,
        ),
        ParameterDef(
            name="existing_workflows",
            type="list",
            description="List of existing workflow summaries for reference",
            required=False,
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
    ]

    outputs = [
        ParameterDef(
            name="yaml",
            type="string",
            description="The generated workflow YAML",
            required=True,
        ),
        ParameterDef(
            name="name",
            type="string",
            description="Name of the created workflow",
            required=True,
        ),
        ParameterDef(
            name="definition_id",
            type="string",
            description="ID of the workflow definition",
            required=True,
        ),
    ]

    SYSTEM_PROMPT = """You are a workflow designer for the Zebra workflow engine.
Create workflow definitions in YAML format.

## Workflow Structure

```yaml
name: "Workflow Name"
description: "What this workflow does"
tags: ["tag1", "tag2"]
version: 1
first_task: task_id

tasks:
  task_id:
    name: "Task Display Name"
    action: llm_call
    auto: true
    properties:
      system_prompt: "Instructions for the LLM"
      prompt: "{{goal}}"  # Use {{goal}} to reference the user's input
      output_key: result_name

routings:
  - from: task1_id
    to: task2_id
```

## Available Actions

- **llm_call**: Call an LLM with a prompt
  - Properties: system_prompt, prompt, output_key, temperature, max_tokens
  - Use {{variable}} to reference process properties or previous outputs

## Guidelines

1. Use descriptive task IDs (e.g., "analyze", "generate", "refine")
2. Always include description and tags for discoverability
3. Use {{goal}} to reference the user's input
4. Use {{previous_output_key}} to chain task outputs
5. Keep workflows focused - do one thing well
6. For multi-step workflows, use routings to connect tasks

## Output

Return ONLY valid YAML, no explanations or markdown code blocks."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute workflow creation."""
        goal = task.properties.get("goal")
        if not goal:
            return TaskResult.fail("No goal provided")

        suggested_name = task.properties.get("suggested_name")
        existing_workflows = task.properties.get("existing_workflows", [])

        # Get LLM provider
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            return TaskResult.fail(f"Failed to get LLM provider: {e}")

        # Build prompt
        prompt = f"Create a workflow for this goal: {goal}\n"

        if suggested_name:
            prompt += f"\nSuggested workflow name: {suggested_name}\n"

        if existing_workflows:
            prompt += "\nExisting workflows for reference (use similar patterns):\n"
            for w in existing_workflows[:5]:  # Limit to 5 examples
                if isinstance(w, dict):
                    name = w.get("name", "Unknown")
                    desc = w.get("description", "")
                    prompt += f"- {name}: {desc}\n"
                else:
                    prompt += f"- {w}\n"

        try:
            response = await provider.complete(
                messages=[
                    Message.system(self.SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.7,  # Higher temperature for creativity
                max_tokens=2000,
            )

            yaml_content = response.content or ""

            # Clean up response - remove markdown code blocks if present
            yaml_content = self._extract_yaml(yaml_content)

            # Validate by parsing
            try:
                definition = load_definition_from_yaml(yaml_content)
            except Exception as e:
                return TaskResult.fail(f"Generated invalid workflow YAML: {e}")

            return TaskResult.ok(
                output={
                    "yaml": yaml_content,
                    "name": definition.name,
                    "definition_id": definition.id,
                }
            )

        except Exception as e:
            return TaskResult.fail(f"Workflow creation failed: {e}")

    def _extract_yaml(self, content: str) -> str:
        """Extract YAML from content, removing markdown code blocks."""
        # Try to extract from code blocks using regex
        patterns = [
            r"```yaml\s*(.*?)\s*```",
            r"```yml\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()

        # No code blocks found, return as-is
        return content.strip()

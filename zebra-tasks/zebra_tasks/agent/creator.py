"""Workflow creator action - uses LLM to create new workflow definitions."""

import re

from zebra.core.models import ProcessDefinition, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml, validate_definition
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.followup import with_previous_run
from zebra_tasks.llm.base import LLMResponse, Message
from zebra_tasks.llm.providers import get_provider

# Generated workflows embed JSON Schemas for human forms, so they are long.
GENERATED_WORKFLOW_MAX_TOKENS = 8000

TRUNCATED_FINISH_REASONS = {"max_tokens", "length"}


def check_generated_workflow(response: LLMResponse, definition: ProcessDefinition) -> str | None:
    """Return an error if a generated workflow is truncated or structurally broken.

    A truncated YAML response can still parse (e.g. the ``routings`` block is
    cut off), yielding a definition whose first task has no outbound routes —
    the process then completes after one task. Catch that before it runs.
    """
    if response.finish_reason in TRUNCATED_FINISH_REASONS:
        return "LLM output was truncated (hit max_tokens)"
    errors = validate_definition(definition)
    if errors:
        return "; ".join(errors)
    return None


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
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the creation result",
            required=False,
            default="created_workflow",
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

    # Split into header + footer; the Available Actions section is injected
    # dynamically at runtime from the action registry so new actions registered
    # as entry points are automatically visible without editing this file.
    _PROMPT_HEADER = """You are a workflow designer for the Zebra workflow engine.
Create workflow definitions in YAML format.

## Workflow Structure

```yaml
name: "Workflow Name"
description: "What this workflow does"
tags: ["tag1", "tag2"]
version: 1
first_task: task_id
result_key: final_output   # the output_key of the task whose value is the main result

tasks:
  task_id:
    name: "Task Display Name"
    action: llm_call
    auto: true
    properties:
      system_prompt: "Instructions for the LLM"
      prompt: "{{goal}}"
      output_key: final_output

routings:
  - from: task1_id
    to: task2_id
```

"""

    _PROMPT_FOOTER = """
## Model aliases for llm_call
The optional `model` property on any `llm_call` task accepts these aliases:
- "haiku" — fastest and cheapest, good for simple extraction or classification
- "sonnet" — balanced quality and speed (default if omitted)
- "opus" — highest quality, use for complex reasoning or creative writing
Only set `model` when a task has clearly different requirements from the default.

## Human input task (auto: false) — Pause for user input via a web form
Set `auto: false` on the task (no action field). Define form fields in
`properties.schema` using standard JSON Schema. The engine pauses the workflow
and the web UI renders a form for the user to fill in.

Supported field types:
- `type: string` — text input; add `format: multiline` for textarea, `enum: [...]` for dropdown
- `type: boolean` — checkbox
- `type: integer` or `type: number` — number input
- `type: string` + `format: email` — email input

Use `required: [field1, field2]`, `minLength`, `maxLength`, `minimum`, `maximum`, `description`.

Example:
```yaml
  get_input:
    name: "Get User Input"
    auto: false
    properties:
      schema:
        type: object
        title: "Provide Information"
        required: [description]
        properties:
          description:
            type: string
            title: "Description"
            format: multiline
            minLength: 10
          priority:
            type: string
            title: "Priority"
            enum: [low, medium, high]
            default: medium
```

For yes/no decisions, use an enum field and conditional routings:
```yaml
routings:
  - from: review
    to: approved_task
    condition: route_name
    name: "yes"
  - from: review
    to: rejected_task
    condition: route_name
    name: "no"
```

## Guidelines

1. Use descriptive task IDs (e.g., "analyze", "generate", "refine", "review")
2. Always include description and tags for discoverability
3. Use {{goal}} to reference the user's input
4. Use {{previous_output_key}} to chain task outputs
5. Keep workflows focused - do one thing well
6. For multi-step workflows, use routings to connect tasks
7. Use human input tasks (auto: false) when the workflow needs information from
   the user, a review/approval step, or any decision that should not be automated
8. Prefer human input tasks over llm_call when the user should provide or verify
   the data themselves (e.g., describing a bug, reviewing a plan, approving output)
9. Always set `result_key` to the output_key of the final task that produces the
   main human-readable result (the answer, recommendation, plan, etc.). This is
   what the UI displays as the workflow output — it should be a clear, readable
   string (markdown is fine), not a raw dict or intermediate value.

## Output

Return ONLY valid YAML, no explanations or markdown code blocks."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute workflow creation."""
        goal = task.properties.get("goal")
        if not goal:
            return TaskResult.fail("No goal provided")

        # Resolve template variables
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        suggested_name = task.properties.get("suggested_name")
        if isinstance(suggested_name, str) and "{{" in suggested_name:
            suggested_name = context.resolve_template(suggested_name)
            # Handle empty string after resolution
            if not suggested_name:
                suggested_name = None

        existing_workflows = task.properties.get("existing_workflows", [])
        if isinstance(existing_workflows, str) and "{{" in existing_workflows:
            import ast
            import json

            resolved = context.resolve_template(existing_workflows)
            try:
                existing_workflows = json.loads(resolved)
            except json.JSONDecodeError:
                try:
                    existing_workflows = ast.literal_eval(resolved)
                except (ValueError, SyntaxError):
                    existing_workflows = []

        # Get LLM provider
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            return TaskResult.fail(f"Failed to get LLM provider: {e}")

        # Emit progress event: creating workflow
        callback = context.extras.get("__progress_callback__")
        if callback:
            await callback("creating_workflow", {"suggested_name": suggested_name})

        # Build prompt (F116: include previous run context for follow-up goals)
        goal_text = with_previous_run(goal, context.process.properties)
        prompt = f"Create a workflow for this goal: {goal_text}\n"

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
            actions_section = context.engine.actions.format_for_prompt(user_facing_only=True)
            system_prompt = self._PROMPT_HEADER + actions_section + self._PROMPT_FOOTER
            response = await provider.complete(
                messages=[
                    Message.system(system_prompt),
                    Message.user(prompt),
                ],
                temperature=0.7,  # Higher temperature for creativity
                max_tokens=GENERATED_WORKFLOW_MAX_TOKENS,
            )

            yaml_content = response.content or ""

            # Clean up response - remove markdown code blocks if present
            yaml_content = self._extract_yaml(yaml_content)

            # Validate by parsing
            try:
                definition = load_definition_from_yaml(yaml_content)
            except Exception as e:
                return TaskResult.fail(f"Generated invalid workflow YAML: {e}")

            problem = check_generated_workflow(response, definition)
            if problem:
                return TaskResult.fail(f"Generated invalid workflow: {problem}")

            # Add workflow to library if available (via context.extras - engine-level injection)
            library = context.extras.get("__workflow_library__")
            if library is not None:
                try:
                    library.add_workflow(yaml_content)
                except Exception:
                    # Log but don't fail - workflow is still valid
                    pass

            # Emit progress event: workflow created/selected
            if callback:
                await callback(
                    "workflow_selected",
                    {
                        "workflow_name": definition.name,
                        "reasoning": f"Created new workflow: {definition.name}",
                        "created_new": True,
                    },
                )

            # Store creation result and set workflow_name for downstream tasks
            output_key = task.properties.get("output_key", "created_workflow")
            output_data = {
                "yaml": yaml_content,
                "name": definition.name,
                "definition_id": definition.id,
            }
            context.set_process_property(output_key, output_data)

            # Set workflow_name for the execute step
            context.set_process_property("workflow_name", definition.name)
            context.set_process_property("created_new", True)

            return TaskResult.ok(output=output_data)

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

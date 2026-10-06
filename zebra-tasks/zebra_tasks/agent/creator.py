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
name: "Topic Briefing"
description: "Research a topic on the web and write a short briefing"
tags: ["research", "summary"]
version: 1
first_task: search
result_key: briefing   # output_key of the task whose value is the main result

tasks:
  search:
    name: "Search the Web"
    action: kagi_search
    auto: true
    properties:
      query: "{{goal}}"
      limit: 5
      output_key: search_results

  write_briefing:
    name: "Write Briefing"
    action: llm_call
    auto: true
    properties:
      system_prompt: "You write concise, well-sourced briefings in markdown."
      prompt: |
        Goal: {{goal}}

        Search results:
        {{search_results.results}}

        Write a one-page briefing that answers the goal, citing URLs.
      output_key: briefing

routings:
  - from: search
    to: write_briefing
```

## Data Flow

- `{{goal}}` is the user's goal text.
- A task's `output_key` names the process property its result is stored under.
  Later tasks read it with `{{output_key}}`.
- `llm_call` stores its response text (a string) under `output_key`. With
  `response_format: json` it stores the parsed JSON object instead.
- Other actions store a dict whose fields are listed under "Outputs" below;
  read one field with `{{output_key.field}}` (e.g. `{{search_results.results}}`).
- Every task's raw result is also stored as `__task_output_<task_id>`. Human
  tasks ignore `output_key`, so read their form fields with
  `{{__task_output_<task_id>.<field>}}`, or the whole form with `{{<task_id>.output}}`.

## Routing

- Routings run when the `from` task completes. Serial routings (the default)
  stop at the first one that fires: two plain routings from one task go to the
  first `to` only.
- Use `parallel: true` on each routing to run branches at the same time, and
  `synchronized: true` on the task where they meet so it waits for all of them.
- `condition: route_name` routings fire only when the task picks that route
  `name`. Only human tasks (auto: false) can pick a route: each route name is
  shown to the user as a button. Never put `route_name` routings after an
  automated task such as `llm_call`; they will never fire and the workflow fails.
- A task with no outgoing routings ends the workflow.

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

For yes/no (or any multi-way) decisions, give the human task `route_name`
routings. Each routing `name` becomes a button on the form; the button the user
clicks decides the route. Do not add a form field for the decision itself:
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
4. Chain tasks through `output_key` values as described in "Data Flow"
5. Keep workflows focused - do one thing well
6. For multi-step workflows, use routings to connect tasks; every task except
   `first_task` must be the `to` of at least one routing
7. Use human input tasks (auto: false) when the workflow needs information from
   the user, a review/approval step, or any decision that should not be automated
8. Prefer human input tasks over llm_call when the user should provide or verify
   the data themselves (e.g., describing a bug, reviewing a plan, approving output)
9. Always set `result_key` to the output_key of the final task that produces the
   main human-readable result (the answer, recommendation, plan, etc.). This is
   what the UI displays as the workflow output — it should be a clear, readable
   string (markdown is fine), not a raw dict or intermediate value.
10. Only use actions that change things outside the workflow (file_write,
    file_move, file_copy, file_delete, python_exec, notifications) when the goal
    explicitly asks for that effect. Put a human review task before any step
    that deletes, overwrites or sends something.

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
            messages = [Message.system(system_prompt), Message.user(prompt)]
            yaml_content, definition, problem, truncated = await self._generate(provider, messages)
            if problem and not truncated:
                # One repair round: show the LLM its YAML and the error.
                messages = messages + [
                    Message.assistant(yaml_content),
                    Message.user(
                        f"That workflow is invalid: {problem}\n"
                        "Return the corrected workflow as YAML only."
                    ),
                ]
                yaml_content, definition, problem, truncated = await self._generate(
                    provider, messages
                )
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

    async def _generate(
        self, provider, messages: list[Message]
    ) -> tuple[str, ProcessDefinition | None, str | None, bool]:
        """Ask the LLM for a workflow and check it.

        Returns:
            (yaml, definition, problem, truncated) — ``problem`` is None when the
            workflow is valid; ``truncated`` is True when the output hit max_tokens.
        """
        response = await provider.complete(
            messages=messages,
            temperature=0.3,  # Structured output; creativity lives in the workflow's own tasks
            max_tokens=GENERATED_WORKFLOW_MAX_TOKENS,
        )
        yaml_content = self._extract_yaml(response.content or "")
        truncated = response.finish_reason in TRUNCATED_FINISH_REASONS
        try:
            definition = load_definition_from_yaml(yaml_content)
        except Exception as e:
            return yaml_content, None, f"YAML did not load: {e}", truncated
        return yaml_content, definition, check_generated_workflow(response, definition), truncated

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

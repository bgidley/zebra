"""WorkflowOptimizerAction - Create and optimize workflows based on evaluation."""

import json
import re
from pathlib import Path
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message

# Matches a pure template reference like "{{some_key}}"
_PURE_TEMPLATE_RE = re.compile(r"^\{\{(\w+)\}\}$")


class WorkflowOptimizerAction(TaskAction):
    """
    Create new workflows or optimize existing ones based on evaluation.

    This action takes improvement priorities from the evaluator and
    generates concrete workflow changes.

    Properties:
        evaluation: Output from WorkflowEvaluatorAction
        workflow_library_path: Path to workflow YAML files
        existing_workflows: Dict of workflow name -> YAML content
        max_changes: Maximum number of changes to make (default: 3)
        dry_run: If True, only generate changes without saving (default: False)
        output_key: Where to store results (default: "optimization_results")

    Output includes:
        - changes_made: List of changes that were made
        - new_workflows: New workflow definitions created
        - modified_workflows: Existing workflows that were modified
        - skipped: Changes that were skipped and why

    Example workflow usage:
        ```yaml
        tasks:
          optimize:
            name: "Optimize Workflows"
            action: workflow_optimizer
            auto: true
            properties:
              evaluation: "{{evaluation}}"
              workflow_library_path: "{{library_path}}"
              existing_workflows: "{{workflow_definitions}}"
              max_changes: 3
              dry_run: false
              output_key: optimization_results
        ```
    """

    description = "Create new workflows or optimize existing ones based on evaluation results."

    inputs = [
        ParameterDef(
            name="evaluation",
            type="dict",
            description="Output from WorkflowEvaluatorAction",
            required=True,
        ),
        ParameterDef(
            name="workflow_library_path",
            type="string",
            description="Path to workflow YAML files for saving",
            required=False,
        ),
        ParameterDef(
            name="existing_workflows",
            type="dict",
            description="Dict of workflow name -> YAML content",
            required=False,
            default={},
        ),
        ParameterDef(
            name="max_changes",
            type="int",
            description="Maximum number of changes to make",
            required=False,
            default=3,
        ),
        ParameterDef(
            name="dry_run",
            type="bool",
            description="If True, only generate changes without saving",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the results",
            required=False,
            default="optimization_results",
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider name",
            required=False,
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
            name="changes_made",
            type="list[dict]",
            description="List of changes that were made",
            required=True,
        ),
        ParameterDef(
            name="new_workflows",
            type="list[dict]",
            description="New workflow definitions created",
            required=True,
        ),
        ParameterDef(
            name="modified_workflows",
            type="list[dict]",
            description="Existing workflows that were modified",
            required=True,
        ),
        ParameterDef(
            name="skipped",
            type="list[dict]",
            description="Changes that were skipped and why",
            required=True,
        ),
        ParameterDef(
            name="dry_run",
            type="bool",
            description="Whether this was a dry run",
            required=True,
        ),
    ]

    SYSTEM_PROMPT = """You are an expert workflow designer for the Zebra workflow engine.
Your task is to create or modify workflow definitions based on improvement recommendations.

## Workflow Structure

```yaml
name: "Workflow Name"
description: "What this workflow does"
tags: ["tag1", "tag2"]
use_when: "Natural language description of when to use this workflow"
version: 1
first_task: task_id

tasks:
  task_id:
    name: "Task Display Name"
    action: llm_call
    auto: true
    properties:
      system_prompt: "Instructions for the LLM"
      prompt: "{{goal}}"
      output_key: result_name

routings:
  - from: task1_id
    to: task2_id
```

## Available Actions

- **llm_call**: Call an LLM with a prompt
  - Properties: system_prompt, prompt, output_key, temperature, max_tokens
  - Use {{variable}} to reference process properties or previous outputs

- **python_exec**: Execute Python code
  - Properties: code, output_key
  - Access props dict for process properties, set result variable

## Guidelines

1. Use descriptive task IDs (snake_case)
2. Always include description, tags, and use_when
3. Use {{goal}} to reference the user's input
4. Use {{previous_output_key}} to chain task outputs
5. Keep workflows focused on one purpose
6. Add clear system prompts that guide the LLM
7. For multi-step tasks, use routings to chain tasks

Output ONLY valid YAML, no explanations or markdown code blocks."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Optimize workflows based on evaluation."""
        # Get inputs — resolve template references while preserving dict types.
        evaluation = self._resolve_property(task, context, "evaluation")
        existing_workflows = self._resolve_property(task, context, "existing_workflows", default={})

        library_path = task.properties.get("workflow_library_path")
        if not library_path:
            library_path = context.process.properties.get("__workflow_library_path__")

        max_changes = task.properties.get("max_changes", 3)
        dry_run = task.properties.get("dry_run", False)
        output_key = task.properties.get("output_key", "optimization_results")

        if not evaluation:
            return TaskResult.fail("No evaluation provided")

        try:
            # Get LLM provider
            provider = self._get_provider(task, context)
            if provider is None:
                return TaskResult.fail("No LLM provider available")

            results = {
                "changes_made": [],
                "new_workflows": [],
                "modified_workflows": [],
                "skipped": [],
                "dry_run": dry_run,
            }

            # Process improvement priorities
            priorities = evaluation.get("improvement_priorities", [])
            new_suggestions = evaluation.get("new_workflow_suggestions", [])

            changes_count = 0

            # Handle new workflow suggestions first
            for suggestion in new_suggestions:
                if changes_count >= max_changes:
                    results["skipped"].append(
                        {
                            "type": "new_workflow",
                            "name": suggestion.get("name"),
                            "reason": "max_changes limit reached",
                        }
                    )
                    continue

                workflow_yaml = await self._create_new_workflow(
                    provider, suggestion, existing_workflows
                )

                if workflow_yaml:
                    name = suggestion.get("name", "new_workflow")
                    results["new_workflows"].append(
                        {
                            "name": name,
                            "yaml": workflow_yaml,
                            "reason": suggestion.get("rationale", ""),
                        }
                    )

                    if not dry_run and library_path:
                        self._save_workflow(library_path, name, workflow_yaml)

                    results["changes_made"].append(
                        {
                            "type": "create",
                            "workflow": name,
                            "description": suggestion.get("description", ""),
                        }
                    )
                    changes_count += 1

            # Handle improvements to existing workflows
            for priority in priorities:
                if changes_count >= max_changes:
                    results["skipped"].append(
                        {
                            "type": priority.get("type"),
                            "target": priority.get("target"),
                            "reason": "max_changes limit reached",
                        }
                    )
                    continue

                if priority.get("type") == "create":
                    # Create new workflow
                    workflow_yaml = await self._create_workflow_from_priority(
                        provider, priority, existing_workflows
                    )

                    if workflow_yaml:
                        name = priority.get("target", "new_workflow")
                        results["new_workflows"].append(
                            {
                                "name": name,
                                "yaml": workflow_yaml,
                                "reason": priority.get("rationale", ""),
                            }
                        )

                        if not dry_run and library_path:
                            self._save_workflow(library_path, name, workflow_yaml)

                        results["changes_made"].append(
                            {
                                "type": "create",
                                "workflow": name,
                                "action": priority.get("action", ""),
                            }
                        )
                        changes_count += 1

                elif priority.get("type") in ("fix", "enhance"):
                    target = priority.get("target")
                    if target in existing_workflows:
                        modified_yaml = await self._modify_workflow(
                            provider,
                            target,
                            existing_workflows[target],
                            priority,
                            evaluation.get("workflow_evaluations", []),
                        )

                        if modified_yaml:
                            results["modified_workflows"].append(
                                {
                                    "name": target,
                                    "original_yaml": existing_workflows[target],
                                    "modified_yaml": modified_yaml,
                                    "reason": priority.get("rationale", ""),
                                }
                            )

                            if not dry_run and library_path:
                                self._save_workflow(library_path, target, modified_yaml)

                            results["changes_made"].append(
                                {
                                    "type": "modify",
                                    "workflow": target,
                                    "action": priority.get("action", ""),
                                }
                            )
                            changes_count += 1
                    else:
                        results["skipped"].append(
                            {
                                "type": priority.get("type"),
                                "target": target,
                                "reason": "workflow not found in existing_workflows",
                            }
                        )

            # Store result
            context.set_process_property(output_key, results)

            return TaskResult.ok(output=results)

        except Exception as e:
            return TaskResult.fail(f"Workflow optimization failed: {str(e)}")

    def _resolve_property(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        key: str,
        default: Any = None,
    ) -> Any:
        """Resolve a task property, preserving non-string types.

        If the raw value is a pure template reference like ``"{{foo}}"``,
        the corresponding process property is returned directly (as a dict,
        list, etc.) instead of being stringified by ``resolve_template``.
        """
        raw = task.properties.get(key, default)
        if not isinstance(raw, str):
            return raw

        m = _PURE_TEMPLATE_RE.match(raw.strip())
        if m:
            prop_name = m.group(1)
            value = context.get_process_property(prop_name)
            if value is not None:
                return value

        # Fall back to string resolution (handles compound templates)
        resolved = context.resolve_template(raw)
        if isinstance(resolved, str):
            try:
                return json.loads(resolved)
            except (json.JSONDecodeError, ValueError):
                pass
        return resolved or default

    def _get_provider(self, task: TaskInstance, context: ExecutionContext):
        """Get the LLM provider to use."""
        from zebra_tasks.llm.providers.registry import get_provider

        provider_name = task.properties.get("provider")
        model = task.properties.get("model")

        if not provider_name:
            provider_name = context.process.properties.get("__llm_provider_name__")
        if not model:
            model = context.process.properties.get("__llm_model__")

        if provider_name:
            return get_provider(provider_name, model)

        return context.process.properties.get("__llm_provider__")

    async def _create_new_workflow(
        self,
        provider,
        suggestion: dict[str, Any],
        existing_workflows: dict[str, str],
    ) -> str | None:
        """Create a new workflow based on a suggestion."""
        prompt = f"""Create a new workflow with the following requirements:

Name: {suggestion.get("name", "New Workflow")}
Description: {suggestion.get("description", "No description provided")}
Use Case: {suggestion.get("use_case", "General purpose")}
Rationale: {suggestion.get("rationale", "")}

"""
        if existing_workflows:
            prompt += "\nExisting workflows for reference (use similar patterns):\n"
            for name, yaml_content in list(existing_workflows.items())[:2]:
                prompt += f"\n{name}:\n{yaml_content[:500]}...\n"

        prompt += "\nCreate a complete, valid YAML workflow definition."

        response = await provider.complete(
            messages=[
                Message.system(self.SYSTEM_PROMPT),
                Message.user(prompt),
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        return self._clean_yaml_response(response.content)

    async def _create_workflow_from_priority(
        self,
        provider,
        priority: dict[str, Any],
        existing_workflows: dict[str, str],
    ) -> str | None:
        """Create a workflow based on an improvement priority."""
        prompt = f"""Create a new workflow to address this improvement priority:

Target: {priority.get("target", "New capability")}
Action needed: {priority.get("action", "")}
Expected impact: {priority.get("expected_impact", "medium")}
Rationale: {priority.get("rationale", "")}

"""
        if existing_workflows:
            prompt += "\nExisting workflows for reference:\n"
            for name in list(existing_workflows.keys())[:3]:
                prompt += f"- {name}\n"

        prompt += "\nCreate a complete, valid YAML workflow definition."

        response = await provider.complete(
            messages=[
                Message.system(self.SYSTEM_PROMPT),
                Message.user(prompt),
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        return self._clean_yaml_response(response.content)

    async def _modify_workflow(
        self,
        provider,
        workflow_name: str,
        current_yaml: str,
        priority: dict[str, Any],
        evaluations: list[dict],
    ) -> str | None:
        """Modify an existing workflow based on evaluation."""
        # Find the specific evaluation for this workflow
        workflow_eval = None
        for ev in evaluations:
            if ev.get("workflow_name") == workflow_name:
                workflow_eval = ev
                break

        prompt = f"""Modify this existing workflow to address the following issues:

Current workflow:
```yaml
{current_yaml}
```

Improvement needed:
- Type: {priority.get("type", "fix")}
- Action: {priority.get("action", "")}
- Rationale: {priority.get("rationale", "")}
"""

        if workflow_eval:
            prompt += f"""
Evaluation findings:
- Effectiveness score: {workflow_eval.get("effectiveness_score", "N/A")}/100
- Weaknesses: {", ".join(workflow_eval.get("weaknesses", []))}
- Suggested improvements: {", ".join(workflow_eval.get("specific_improvements", []))}
"""

        prompt += """
Provide the complete modified YAML workflow. Keep what works, fix what doesn't.
Maintain the same name and general purpose, but improve the implementation."""

        response = await provider.complete(
            messages=[
                Message.system(self.SYSTEM_PROMPT),
                Message.user(prompt),
            ],
            temperature=0.5,
            max_tokens=2000,
        )

        return self._clean_yaml_response(response.content)

    def _clean_yaml_response(self, content: str | None) -> str | None:
        """Clean YAML from LLM response."""
        if not content:
            return None

        # Remove markdown code blocks
        if "```yaml" in content:
            start = content.index("```yaml") + 7
            end = content.index("```", start)
            content = content[start:end].strip()
        elif "```yml" in content:
            start = content.index("```yml") + 6
            end = content.index("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end].strip()

        return content.strip()

    def _save_workflow(self, library_path: str, name: str, yaml_content: str) -> None:
        """Save a workflow to the library."""
        path = Path(library_path)
        path.mkdir(parents=True, exist_ok=True)

        # Create filename from name
        filename = name.lower().replace(" ", "_").replace("-", "_")
        filename = "".join(c for c in filename if c.isalnum() or c == "_")
        filepath = path / f"{filename}.yaml"

        # Don't overwrite if exists - add suffix
        counter = 1
        while filepath.exists():
            filepath = path / f"{filename}_{counter}.yaml"
            counter += 1

        filepath.write_text(yaml_content)

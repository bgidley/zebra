"""WorkflowOptimizerAction - Create and optimize workflows based on evaluation."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.creator import (
    GENERATED_WORKFLOW_MAX_TOKENS,
    TRUNCATED_FINISH_REASONS,
    check_generated_workflow,
)
from zebra_tasks.llm.base import LLMResponse, Message

logger = logging.getLogger(__name__)

# Extra attempts (at double the token budget) when the LLM output is truncated.
TRUNCATION_RETRIES = 1

# Priority ``source`` marking continuation-driven proposals (F136).
CONTINUATION = "continuation"

# Matches a pure template reference like "{{some_key}}"
_PURE_TEMPLATE_RE = re.compile(r"^\{\{(\w+)\}\}$")

# Provenance tag for LLM-written workflows (mirrors zebra_agent.library, #148).
LLM_DEFINED_TAG = "llm-defined"


def _yaml_tags(yaml_content: str) -> list:
    """Return the ``tags`` list of a workflow YAML, or [] if unreadable."""
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return []
    tags = data.get("tags") if isinstance(data, dict) else None
    return tags if isinstance(tags, list) else []


def _tag_llm_defined(yaml_content: str) -> str:
    """Add the ``llm-defined`` tag via the library helper, if zebra-agent is installed."""
    try:
        from zebra_agent.library import tag_llm_defined
    except ImportError:
        return yaml_content
    return tag_llm_defined(yaml_content)


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
        - failed_changes: Changes rejected because the generated YAML was
          truncated or invalid (never saved, never listed in changes_made)
        - continuation_changes: Outcome of continuation-driven priorities
          (``source: continuation``), which are applied before other changes

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
            name="failed_changes",
            type="list[dict]",
            description=(
                "Changes rejected because the generated workflow was truncated or invalid; "
                "these were not saved"
            ),
            required=True,
        ),
        ParameterDef(
            name="continuation_changes",
            type="list[dict]",
            description=(
                "Outcome (made/failed/skipped) of each continuation-driven priority (F136)"
            ),
            required=True,
        ),
        ParameterDef(
            name="dry_run",
            type="bool",
            description="Whether this was a dry run",
            required=True,
        ),
    ]

    # Split into header + footer; Available Actions injected dynamically at runtime.
    _PROMPT_HEADER = """You are an expert workflow designer for the Zebra workflow engine.
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

"""

    _PROMPT_FOOTER = """
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

            # Build system prompt dynamically so newly-registered actions are visible.
            actions_section = context.engine.actions.format_for_prompt(user_facing_only=True)
            system_prompt = self._PROMPT_HEADER + actions_section + self._PROMPT_FOOTER

            results = {
                "changes_made": [],
                "new_workflows": [],
                "modified_workflows": [],
                "skipped": [],
                "failed_changes": [],
                "continuation_changes": [],
                "dry_run": dry_run,
            }

            # Process improvement priorities. Continuation-driven ones (F136) go first:
            # they are concrete, user-evidenced fixes.
            priorities = evaluation.get("improvement_priorities", [])
            new_suggestions = evaluation.get("new_workflow_suggestions", [])
            continuation_priorities = [p for p in priorities if p.get("source") == CONTINUATION]
            other_priorities = [p for p in priorities if p.get("source") != CONTINUATION]

            changes_count = 0
            apply_args = (provider, evaluation, existing_workflows, system_prompt, context)

            for priority in continuation_priorities:
                if changes_count >= max_changes:
                    self._skip_priority(results, priority, "max_changes limit reached")
                    continue
                if await self._apply_priority(
                    results, priority, *apply_args, dry_run=dry_run, library_path=library_path
                ):
                    changes_count += 1

            # Then new workflow suggestions
            for suggestion in new_suggestions:
                name = suggestion.get("name", "new_workflow")
                if changes_count >= max_changes:
                    results["skipped"].append(
                        {
                            "type": "new_workflow",
                            "name": name,
                            "reason": "max_changes limit reached",
                        }
                    )
                    continue

                workflow_yaml, error = await self._create_new_workflow(
                    provider, suggestion, existing_workflows, system_prompt, context
                )
                if error:
                    self._record_failure(results, "create", name, error)
                    continue

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

            # Then the remaining improvements
            for priority in other_priorities:
                if changes_count >= max_changes:
                    self._skip_priority(results, priority, "max_changes limit reached")
                    continue
                if await self._apply_priority(
                    results, priority, *apply_args, dry_run=dry_run, library_path=library_path
                ):
                    changes_count += 1

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
        system_prompt: str,
        context: ExecutionContext,
    ) -> tuple[str | None, str | None]:
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

        return await self._generate_workflow_yaml(
            provider, system_prompt, prompt, temperature=0.7, context=context
        )

    async def _create_workflow_from_priority(
        self,
        provider,
        priority: dict[str, Any],
        existing_workflows: dict[str, str],
        system_prompt: str,
        context: ExecutionContext,
    ) -> tuple[str | None, str | None]:
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

        return await self._generate_workflow_yaml(
            provider, system_prompt, prompt, temperature=0.7, context=context
        )

    async def _modify_workflow(
        self,
        provider,
        workflow_name: str,
        current_yaml: str,
        priority: dict[str, Any],
        evaluations: list[dict],
        system_prompt: str,
        context: ExecutionContext,
    ) -> tuple[str | None, str | None]:
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

        return await self._generate_workflow_yaml(
            provider, system_prompt, prompt, temperature=0.5, context=context
        )

    def _clean_yaml_response(self, content: str | None) -> str | None:
        """Strip markdown code fences from an LLM response.

        Tolerates an unterminated fence (a symptom of truncation) by taking
        everything after the opening fence; validation then rejects it.
        """
        if not content:
            return None

        for fence in ("```yaml", "```yml", "```"):
            start = content.find(fence)
            if start == -1:
                continue
            start += len(fence)
            end = content.find("```", start)
            content = content[start:] if end == -1 else content[start:end]
            break

        return content.strip() or None

    async def _generate_workflow_yaml(
        self,
        provider,
        system_prompt: str,
        prompt: str,
        temperature: float,
        context: ExecutionContext,
    ) -> tuple[str | None, str | None]:
        """Ask the LLM for a workflow and validate it.

        Retries once with double the token budget when the response is
        truncated. Returns ``(yaml, None)`` on success or ``(None, reason)``
        when the output must not be saved.
        """
        messages = [Message.system(system_prompt), Message.user(prompt)]
        max_tokens = GENERATED_WORKFLOW_MAX_TOKENS
        response = None
        for attempt in range(1 + TRUNCATION_RETRIES):
            try:
                response = await provider.complete(
                    messages=messages, temperature=temperature, max_tokens=max_tokens
                )
            except Exception as e:
                return None, f"LLM call failed: {e}"
            if response.finish_reason not in TRUNCATED_FINISH_REASONS:
                break
            logger.warning(
                "workflow_optimizer: LLM output truncated at max_tokens=%d (attempt %d)",
                max_tokens,
                attempt + 1,
            )
            max_tokens *= 2

        yaml_content = self._clean_yaml_response(response.content)
        error = self._validate_workflow_yaml(response, yaml_content, context)
        if error:
            return None, error
        return yaml_content, None

    def _validate_workflow_yaml(
        self, response: LLMResponse, yaml_content: str | None, context: ExecutionContext
    ) -> str | None:
        """Return why a generated workflow is unusable, or None if it is valid.

        Uses the same loader as the workflow library, then the shared generator
        checks (truncation, ``validate_definition``), then the action registry.
        """
        if not yaml_content:
            return "LLM returned no workflow YAML"
        try:
            definition = load_definition_from_yaml(yaml_content)
        except Exception as e:
            if response.finish_reason in TRUNCATED_FINISH_REASONS:
                return f"LLM output was truncated (hit max_tokens): {e}"
            return f"Invalid workflow YAML: {e}"

        problem = check_generated_workflow(response, definition)
        if problem:
            return problem

        registry = getattr(getattr(context, "engine", None), "actions", None)
        if registry is not None:
            unknown = sorted(
                {
                    t.action
                    for t in definition.tasks.values()
                    if t.action and not registry.has_action(t.action)
                }
            )
            if unknown:
                return f"Unregistered action(s): {', '.join(unknown)}"
        return None

    async def _apply_priority(
        self,
        results: dict[str, Any],
        priority: dict[str, Any],
        provider,
        evaluation: dict[str, Any],
        existing_workflows: dict[str, str],
        system_prompt: str,
        context: ExecutionContext,
        *,
        dry_run: bool,
        library_path: str | None,
    ) -> bool:
        """Generate, validate and (unless dry run) save one priority's change.

        Returns True when a change was made (counts toward ``max_changes``).
        """
        ptype = priority.get("type")
        if ptype == "create":
            name = priority.get("target", "new_workflow")
            workflow_yaml, error = await self._create_workflow_from_priority(
                provider, priority, existing_workflows, system_prompt, context
            )
            if error:
                self._record_failure(results, "create", name, error)
                self._track_continuation(results, priority, "failed", error)
                return False
            results["new_workflows"].append(
                {"name": name, "yaml": workflow_yaml, "reason": priority.get("rationale", "")}
            )
            if not dry_run and library_path:
                self._save_workflow(library_path, name, workflow_yaml)
            self._record_change(results, priority, "create", name)
            return True

        if ptype in ("fix", "enhance"):
            target = priority.get("target")
            if target not in existing_workflows:
                self._skip_priority(results, priority, "workflow not found in existing_workflows")
                return False
            modified_yaml, error = await self._modify_workflow(
                provider,
                target,
                existing_workflows[target],
                priority,
                evaluation.get("workflow_evaluations", []),
                system_prompt,
                context,
            )
            if error:
                self._record_failure(results, "modify", target, error)
                self._track_continuation(results, priority, "failed", error)
                return False
            results["modified_workflows"].append(
                {
                    "name": target,
                    "original_yaml": existing_workflows[target],
                    "modified_yaml": modified_yaml,
                    "reason": priority.get("rationale", ""),
                }
            )
            if not dry_run and library_path:
                # A modified workflow keeps its provenance: hand-written stays hand-written.
                self._save_workflow(
                    library_path,
                    target,
                    modified_yaml,
                    llm_defined=LLM_DEFINED_TAG in _yaml_tags(existing_workflows[target]),
                )
            self._record_change(results, priority, "modify", target)
            return True

        return False

    def _record_change(
        self, results: dict[str, Any], priority: dict[str, Any], change_type: str, name: str
    ) -> None:
        change = {"type": change_type, "workflow": name, "action": priority.get("action", "")}
        if priority.get("source"):
            change["source"] = priority["source"]
        results["changes_made"].append(change)
        self._track_continuation(results, priority, "made")

    def _skip_priority(self, results: dict[str, Any], priority: dict[str, Any], reason: str):
        results["skipped"].append(
            {"type": priority.get("type"), "target": priority.get("target"), "reason": reason}
        )
        self._track_continuation(results, priority, "skipped", reason)

    @staticmethod
    def _track_continuation(
        results: dict[str, Any], priority: dict[str, Any], status: str, reason: str = ""
    ) -> None:
        """Record the outcome of a continuation-driven priority for the summary (F136)."""
        if priority.get("source") != CONTINUATION:
            return
        results["continuation_changes"].append(
            {
                "type": priority.get("type"),
                "kind": priority.get("kind"),
                "workflow": priority.get("target"),
                "status": status,
                "reason": reason,
            }
        )

    @staticmethod
    def _record_failure(results: dict[str, Any], change_type: str, name: str, reason: str):
        """Record a rejected change so it is reported but never claimed as made."""
        logger.warning("workflow_optimizer rejected %s of %r: %s", change_type, name, reason)
        results["failed_changes"].append({"type": change_type, "workflow": name, "reason": reason})

    def _save_workflow(
        self, library_path: str, name: str, yaml_content: str, llm_defined: bool = True
    ) -> None:
        """Save a workflow to the library.

        New workflows are tagged ``llm-defined`` so the dream-cycle curator may
        retire them when unused (#148).
        """
        if llm_defined:
            yaml_content = _tag_llm_defined(yaml_content)
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

"""WorkflowEvaluatorAction - LLM-based evaluation of workflow effectiveness."""

import json
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

from zebra_tasks.llm.base import Message


class WorkflowEvaluatorAction(TaskAction):
    """
    Use LLM to evaluate workflow effectiveness and identify improvements.

    This action analyzes metrics and workflow definitions to provide
    intelligent recommendations for improvement.

    Properties:
        metrics_analysis: Output from MetricsAnalyzerAction
        workflow_definitions: Dict of workflow name -> YAML content
        output_key: Where to store evaluation (default: "workflow_evaluation")

    Output includes:
        - overall_assessment: Summary of system health
        - workflow_evaluations: Per-workflow detailed evaluation
        - improvement_priorities: Ranked list of improvements
        - new_workflow_suggestions: Ideas for new workflows
        - optimization_opportunities: Ways to improve existing workflows

    Example workflow usage:
        ```yaml
        tasks:
          evaluate:
            name: "Evaluate Workflows"
            action: workflow_evaluator
            auto: true
            properties:
              metrics_analysis: "{{metrics_analysis}}"
              workflow_definitions: "{{workflow_definitions}}"
              output_key: evaluation
        ```
    """

    SYSTEM_PROMPT = """You are an AI workflow optimization expert. Your role is to analyze
workflow performance metrics and definitions to identify improvement opportunities.

You will receive:
1. Performance metrics (success rates, usage, failures)
2. Workflow definitions (YAML)

Your task is to:
1. Assess overall system health
2. Identify problematic workflows
3. Suggest specific improvements
4. Recommend new workflows for capability gaps
5. Prioritize changes by impact

Be specific and actionable in your recommendations. Focus on:
- Root causes of failures
- Patterns in unsuccessful goals
- Workflow design issues
- Missing capabilities

Respond with JSON only:
{
    "overall_assessment": {
        "health_score": 0-100,
        "summary": "brief overall assessment",
        "key_issues": ["issue1", "issue2"]
    },
    "workflow_evaluations": [
        {
            "workflow_name": "name",
            "effectiveness_score": 0-100,
            "strengths": ["..."],
            "weaknesses": ["..."],
            "specific_improvements": ["..."]
        }
    ],
    "improvement_priorities": [
        {
            "priority": 1,
            "type": "fix|enhance|create",
            "target": "workflow name or description",
            "action": "specific action to take",
            "expected_impact": "high|medium|low",
            "rationale": "why this matters"
        }
    ],
    "new_workflow_suggestions": [
        {
            "name": "suggested name",
            "description": "what it does",
            "use_case": "when to use it",
            "rationale": "why needed based on failure patterns"
        }
    ]
}"""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Evaluate workflows using LLM."""
        # Get inputs
        metrics_analysis = task.properties.get("metrics_analysis")
        if isinstance(metrics_analysis, str):
            metrics_analysis = context.resolve_template(metrics_analysis)
            if isinstance(metrics_analysis, str):
                try:
                    metrics_analysis = json.loads(metrics_analysis)
                except json.JSONDecodeError:
                    pass

        workflow_definitions = task.properties.get("workflow_definitions", {})
        if isinstance(workflow_definitions, str):
            workflow_definitions = context.resolve_template(workflow_definitions)

        output_key = task.properties.get("output_key", "workflow_evaluation")

        if not metrics_analysis:
            return TaskResult.fail("No metrics_analysis provided")

        try:
            # Get LLM provider
            provider = self._get_provider(task, context)
            if provider is None:
                return TaskResult.fail("No LLM provider available")

            # Build evaluation prompt
            prompt = self._build_prompt(metrics_analysis, workflow_definitions)

            # Call LLM
            response = await provider.complete(
                messages=[
                    Message.system(self.SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.3,
                max_tokens=4000,
            )

            # Parse response
            content = response.content or ""
            evaluation = self._parse_response(content)

            # Store result
            context.set_process_property(output_key, evaluation)

            # Track tokens
            current = context.get_process_property("__total_tokens__", 0)
            context.set_process_property(
                "__total_tokens__", current + response.usage.total_tokens
            )

            return TaskResult.ok(output=evaluation)

        except Exception as e:
            return TaskResult.fail(f"Workflow evaluation failed: {str(e)}")

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

    def _build_prompt(
        self, metrics_analysis: dict[str, Any], workflow_definitions: dict[str, str]
    ) -> str:
        """Build the evaluation prompt."""
        prompt_parts = ["## Performance Metrics Analysis\n"]

        # Add summary stats
        prompt_parts.append(f"Analysis period: {metrics_analysis.get('analysis_period_days', 'N/A')} days")
        prompt_parts.append(f"Total runs: {metrics_analysis.get('total_runs_analyzed', 0)}")
        prompt_parts.append(f"Unique workflows: {metrics_analysis.get('unique_workflows', 0)}")
        prompt_parts.append("")

        # Add workflow stats
        prompt_parts.append("### Workflow Statistics")
        for ws in metrics_analysis.get("workflow_stats", []):
            prompt_parts.append(
                f"- {ws['workflow_name']}: {ws['total_runs']} runs, "
                f"{ws['success_rate']*100:.0f}% success, "
                f"avg rating: {ws.get('avg_rating', 'N/A')}"
            )
        prompt_parts.append("")

        # Add low performers
        low_performers = metrics_analysis.get("low_performers", [])
        if low_performers:
            prompt_parts.append("### Low-Performing Workflows (< 70% success)")
            for lp in low_performers:
                prompt_parts.append(
                    f"- {lp['workflow_name']}: {lp['success_rate']*100:.0f}% success"
                )
            prompt_parts.append("")

        # Add failure patterns
        failure_patterns = metrics_analysis.get("failure_patterns", [])
        if failure_patterns:
            prompt_parts.append("### Failure Patterns")
            for fp in failure_patterns:
                prompt_parts.append(f"- {fp['workflow_name']}: {fp['failure_count']} failures")
                for error, count in fp.get("error_types", {}).items():
                    prompt_parts.append(f"  - {error}: {count} times")
                if fp.get("sample_goals"):
                    prompt_parts.append("  Sample failed goals:")
                    for goal in fp["sample_goals"]:
                        prompt_parts.append(f"    - {goal}")
            prompt_parts.append("")

        # Add recommendations from metrics
        recommendations = metrics_analysis.get("recommendations", [])
        if recommendations:
            prompt_parts.append("### Initial Recommendations from Metrics")
            for rec in recommendations:
                prompt_parts.append(f"- {rec}")
            prompt_parts.append("")

        # Add workflow definitions
        if workflow_definitions:
            prompt_parts.append("## Workflow Definitions\n")
            for name, yaml_content in workflow_definitions.items():
                prompt_parts.append(f"### {name}")
                prompt_parts.append("```yaml")
                # Truncate long workflows
                if len(yaml_content) > 2000:
                    prompt_parts.append(yaml_content[:2000] + "\n... (truncated)")
                else:
                    prompt_parts.append(yaml_content)
                prompt_parts.append("```\n")

        prompt_parts.append(
            "\nBased on this analysis, provide a comprehensive evaluation with "
            "specific, actionable improvement recommendations."
        )

        return "\n".join(prompt_parts)

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse the LLM response."""
        import re

        # Try to extract JSON from code blocks
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                content = match.group(1).strip()
                break

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Return structured response with raw content
            return {
                "overall_assessment": {
                    "health_score": 50,
                    "summary": "Unable to parse structured response",
                    "key_issues": ["Response parsing failed"],
                },
                "raw_response": content,
                "workflow_evaluations": [],
                "improvement_priorities": [],
                "new_workflow_suggestions": [],
            }

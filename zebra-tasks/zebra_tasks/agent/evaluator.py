"""WorkflowEvaluatorAction - LLM-based evaluation of workflow effectiveness."""

import json
import logging
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.leak_guard import run_texts_from_metrics
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import LLMJSONError, complete_json, describe_failure

logger = logging.getLogger(__name__)

# Matches a pure template reference like "{{some_key}}"
_PURE_TEMPLATE_RE = re.compile(r"^\{\{(\w+)\}\}$")

# The evaluation is long; 4000 truncated it in prod (#195)
DEFAULT_MAX_TOKENS = 8000

# Characters of workflow YAML the prompt may hold. Definitions go in whole or not at all:
# a cut-off definition made the evaluation reason about steps it could not see (#254).
DEFAULT_MAX_DEFINITION_CHARS = 120_000


def select_definitions(
    workflow_definitions: dict[str, str],
    metrics_analysis: dict[str, Any],
    max_chars: int = DEFAULT_MAX_DEFINITION_CHARS,
) -> tuple[list[str], list[str]]:
    """Choose which whole definitions fit in ``max_chars``, most relevant first.

    Order: workflows with failures (most first), low performers (lowest success first),
    other workflows that ran (most runs first), then the rest by name. A definition that
    does not fit is skipped; smaller ones after it can still fit.

    Returns:
        ``(shown, omitted)`` workflow names, each in relevance order.
    """
    failing = sorted(
        metrics_analysis.get("failure_patterns", []), key=lambda f: -f.get("failure_count", 0)
    )
    low = sorted(metrics_analysis.get("low_performers", []), key=lambda w: w.get("success_rate", 0))
    ran = sorted(metrics_analysis.get("workflow_stats", []), key=lambda w: -w.get("total_runs", 0))
    ranked = [w["workflow_name"] for w in [*failing, *low, *ran] if w.get("workflow_name")]
    order = list(dict.fromkeys(n for n in ranked if n in workflow_definitions))
    order += sorted(n for n in workflow_definitions if n not in order)

    shown: list[str] = []
    omitted: list[str] = []
    used = 0
    for name in order:
        size = len(workflow_definitions[name] or "")
        if used + size <= max_chars:
            shown.append(name)
            used += size
        else:
            omitted.append(name)
    return shown, omitted


class WorkflowEvaluatorAction(TaskAction):
    """
    Use LLM to evaluate workflow effectiveness and identify improvements.

    This action analyzes metrics and workflow definitions to provide
    intelligent recommendations for improvement.

    Properties:
        metrics_analysis: Output from MetricsAnalyzerAction
        workflow_definitions: Dict of workflow name -> YAML content
        output_key: Where to store evaluation (default: "workflow_evaluation")
        max_tokens: Reply token budget (default 8000)
        max_definition_chars: Characters of workflow YAML to show (default 120000); each
            definition is shown whole or named as not shown (``select_definitions``, #254)

    An unparseable reply is retried once (``complete_json``). If that fails too,
    the evaluation is a fallback whose key issue names the cause and whose
    ``parse_failure`` holds the error, finish_reason and raw reply (#195).

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

    description = "Use LLM to evaluate workflow effectiveness and identify improvements."

    inputs = [
        ParameterDef(
            name="metrics_analysis",
            type="dict",
            description="Output from MetricsAnalyzerAction",
            required=True,
        ),
        ParameterDef(
            name="workflow_definitions",
            type="dict",
            description="Dict of workflow name -> YAML content",
            required=False,
            default={},
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the evaluation",
            required=False,
            default="workflow_evaluation",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="LLM model name",
            required=False,
        ),
        ParameterDef(
            name="max_tokens",
            type="int",
            description="Token budget for the reply; doubled on a retry after truncation",
            required=False,
            default=DEFAULT_MAX_TOKENS,
        ),
        ParameterDef(
            name="max_definition_chars",
            type="int",
            description="Characters of workflow YAML to show; definitions are never cut",
            required=False,
            default=DEFAULT_MAX_DEFINITION_CHARS,
        ),
    ]

    outputs = [
        ParameterDef(
            name="overall_assessment",
            type="dict",
            description="Summary of system health with health_score, summary, key_issues",
            required=True,
        ),
        ParameterDef(
            name="workflow_evaluations",
            type="list[dict]",
            description="Per-workflow detailed evaluation",
            required=True,
        ),
        ParameterDef(
            name="improvement_priorities",
            type="list[dict]",
            description="Ranked list of improvements with priority, type, target, action",
            required=True,
        ),
        ParameterDef(
            name="new_workflow_suggestions",
            type="list[dict]",
            description="Ideas for new workflows with name, description, use_case",
            required=True,
        ),
        ParameterDef(
            name="definitions_shown",
            type="list[str]",
            description="Workflows whose whole definition the evaluation saw",
            required=False,
        ),
        ParameterDef(
            name="definitions_omitted",
            type="list[str]",
            description="Workflows named but not shown: over max_definition_chars",
            required=False,
        ),
    ]

    SYSTEM_PROMPT = """You are an AI workflow optimization expert. Your role is to analyze
workflow performance metrics and definitions to identify improvement opportunities.

You will receive:
1. Performance metrics (success rates, usage, failures)
2. Workflow definitions (YAML). Each one shown is complete. Workflows listed under
   "Not shown" exist but their definitions were not provided: make no claims about
   their steps, routing or safety controls.

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
- Continued goals: a workflow users had to continue did not fully satisfy them;
  use their comments and the steps they added afterwards to improve it

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
        # Get inputs — resolve template references while preserving dict types.
        # When a YAML property is "{{some_key}}", resolve_template would
        # stringify the dict via str().  Instead, fetch the process property
        # directly so the original dict is preserved.
        metrics_analysis = self._resolve_property(task, context, "metrics_analysis")
        workflow_definitions = self._resolve_property(
            task, context, "workflow_definitions", default={}
        )

        output_key = task.properties.get("output_key", "workflow_evaluation")

        if not metrics_analysis:
            return TaskResult.fail("No metrics_analysis provided")

        try:
            # Get LLM provider
            provider = get_llm(model_for(task, context), context)

            # Build evaluation prompt
            max_definition_chars = int(
                task.properties.get("max_definition_chars", DEFAULT_MAX_DEFINITION_CHARS)
            )
            shown, omitted = select_definitions(
                workflow_definitions or {}, metrics_analysis, max_definition_chars
            )
            logger.info(
                "workflow_evaluator: %d definitions shown whole, %d not shown (budget %d chars)",
                len(shown),
                len(omitted),
                max_definition_chars,
            )
            prompt = self._build_prompt(
                metrics_analysis, workflow_definitions, max_definition_chars
            )

            # Call LLM; an unusable reply is retried once (#195)
            max_tokens = int(task.properties.get("max_tokens", DEFAULT_MAX_TOKENS))
            try:
                evaluation = await complete_json(
                    provider,
                    [Message.system(self.SYSTEM_PROMPT), Message.user(prompt)],
                    temperature=0.3,
                    max_tokens=max_tokens,
                )
            except LLMJSONError as e:
                evaluation = self._fallback_evaluation(e.failure)
            if not isinstance(evaluation, dict):
                evaluation = self._fallback_evaluation(
                    {
                        "error": f"expected a JSON object, got {type(evaluation).__name__}",
                        "finish_reason": None,
                        "truncated": False,
                        "attempts": 1,
                        "raw_response": json.dumps(evaluation)[:4000],
                    }
                )
            self._merge_continuation_proposals(
                evaluation, metrics_analysis, workflow_definitions or {}
            )
            # The run texts this prompt showed, for the optimizer's leak guard (#237)
            evaluation["run_exposure"] = run_texts_from_metrics(metrics_analysis)
            # What the judgement was based on (#254)
            evaluation["definitions_shown"] = shown
            evaluation["definitions_omitted"] = omitted

            # Store result
            context.set_process_property(output_key, evaluation)

            return TaskResult.ok(output=evaluation)

        except Exception as e:
            return TaskResult.fail(f"Workflow evaluation failed: {str(e)}")

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

    def _build_prompt(
        self,
        metrics_analysis: dict[str, Any],
        workflow_definitions: dict[str, str],
        max_definition_chars: int = DEFAULT_MAX_DEFINITION_CHARS,
    ) -> str:
        """Build the evaluation prompt."""
        prompt_parts = ["## Performance Metrics Analysis\n"]

        # Add summary stats
        prompt_parts.append(
            f"Analysis period: {metrics_analysis.get('analysis_period_days', 'N/A')} days"
        )
        prompt_parts.append(f"Total runs: {metrics_analysis.get('total_runs_analyzed', 0)}")
        prompt_parts.append(f"Unique workflows: {metrics_analysis.get('unique_workflows', 0)}")
        prompt_parts.append("")

        # Add workflow stats
        prompt_parts.append("### Workflow Statistics")
        for ws in metrics_analysis.get("workflow_stats", []):
            prompt_parts.append(
                f"- {ws['workflow_name']}: {ws['total_runs']} runs, "
                f"{ws['success_rate'] * 100:.0f}% success, "
                f"{ws.get('continuation_rate', 0) * 100:.0f}% continued, "
                f"avg rating: {ws.get('avg_rating', 'N/A')}"
            )
        prompt_parts.append("")

        prompt_parts.extend(self._continuation_section(metrics_analysis))

        # Add low performers
        low_performers = metrics_analysis.get("low_performers", [])
        if low_performers:
            prompt_parts.append("### Low-Performing Workflows (< 70% success)")
            for lp in low_performers:
                prompt_parts.append(
                    f"- {lp['workflow_name']}: {lp['success_rate'] * 100:.0f}% success"
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

        # Add workflow definitions, each whole (#254)
        if workflow_definitions:
            shown, omitted = select_definitions(
                workflow_definitions, metrics_analysis, max_definition_chars
            )
            prompt_parts.append("## Workflow Definitions\n")
            for name in shown:
                prompt_parts.append(f"### {name}")
                prompt_parts.append("```yaml")
                prompt_parts.append(workflow_definitions[name])
                prompt_parts.append("```\n")
            if omitted:
                prompt_parts.append(
                    "### Not shown\nThese workflows exist, but their definitions were not "
                    "provided (over the size budget):"
                )
                prompt_parts.extend(f"- {name}" for name in omitted)
                prompt_parts.append("")

        prompt_parts.append(
            "\nBased on this analysis, provide a comprehensive evaluation with "
            "specific, actionable improvement recommendations."
        )

        return "\n".join(prompt_parts)

    @staticmethod
    def _continuation_section(metrics_analysis: dict[str, Any]) -> list[str]:
        """Render continuation findings (F136) for the evaluation prompt."""
        ca = metrics_analysis.get("continuation_analysis") or {}
        if not ca.get("total_continuations"):
            return []
        parts = [
            "### Continued Goals (user had to carry on after the workflow finished)",
            f"Total continuations: {ca['total_continuations']}",
        ]
        for fc in ca.get("frequently_continued", []):
            parts.append(
                f"- {fc['workflow_name']}: continued {fc['continuation_count']} times, "
                f"into {fc.get('continued_into', {})}, decisions {fc.get('decisions', {})}"
            )
            for comment in fc.get("comments", []):
                parts.append(f'  - user said: "{comment}"')
            if fc.get("added_steps"):
                parts.append(f"  - steps added afterwards: {', '.join(fc['added_steps'])}")
        for gap in ca.get("capability_gaps", []):
            parts.append(
                f"- Missing capability after {gap['original_workflow']}: a new workflow "
                f"'{gap['continuation_workflow']}' was needed "
                f"({gap.get('comment') or gap.get('rationale') or 'no comment'})"
            )
        if ca.get("proposals"):
            parts.append("Continuation-driven proposals (already queued for the optimizer):")
            for p in ca["proposals"]:
                parts.append(f"- {p['type']} {p['target']}: {p['action']}")
        parts.append("")
        return parts

    @staticmethod
    def _merge_continuation_proposals(
        evaluation: dict[str, Any],
        metrics_analysis: dict[str, Any],
        workflow_definitions: dict[str, Any],
    ) -> None:
        """Prepend continuation proposals to improvement_priorities (F136).

        Guarantees the deterministic proposals reach the optimizer even when the
        LLM leaves them out. A promote proposal for a workflow that is not in the
        library becomes a ``create``. Skips any (type, target) the LLM already chose.
        """
        ca = metrics_analysis.get("continuation_analysis") or {}
        proposals = ca.get("proposals") or []
        if not proposals:
            return
        llm_priorities = evaluation.get("improvement_priorities") or []
        existing = {(p.get("type"), p.get("target")) for p in llm_priorities}
        merged = []
        for proposal in proposals:
            p = dict(proposal)
            if p.get("kind") == "promote" and p["target"] not in workflow_definitions:
                p["type"] = "create"
            if (p["type"], p["target"]) in existing:
                continue
            existing.add((p["type"], p["target"]))
            merged.append(p)
        combined = merged + list(llm_priorities)
        for i, p in enumerate(combined, start=1):
            p["priority"] = i
        evaluation["improvement_priorities"] = combined
        evaluation["continuation_proposals"] = merged

    @staticmethod
    def _fallback_evaluation(failure: dict[str, Any]) -> dict[str, Any]:
        """Evaluation recorded when no usable reply was obtained, naming the cause (#195)."""
        return {
            "overall_assessment": {
                "health_score": 50,
                "summary": "Unable to parse structured response",
                "key_issues": [f"Evaluator reply unusable: {describe_failure(failure)}"],
            },
            "parse_failure": failure,
            "raw_response": failure.get("raw_response", ""),
            "workflow_evaluations": [],
            "improvement_priorities": [],
            "new_workflow_suggestions": [],
        }

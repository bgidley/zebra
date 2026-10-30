"""MetricsAnalyzerAction - Analyze workflow performance metrics.

Uses the MetricsStore interface from engine.extras to query run data,
ensuring compatibility with all storage backends (InMemory, Django ORM, etc.).
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.continuation_analysis import (
    analyze_continuations,
    empty_continuation_analysis,
)
from zebra_tasks.agent.run_kinds import GOAL_RUN, SYSTEM_RUN, SYSTEM_TAG, TOOL_RUN, run_kind
from zebra_tasks.agent.zebra_source import is_expected_miss

logger = logging.getLogger(__name__)


class MetricsAnalyzerAction(TaskAction):
    """
    Analyze workflow performance metrics via the MetricsStore interface.

    This action reads metrics data through the injected MetricsStore and
    produces analysis that can be used by the agent to identify improvement
    opportunities.

    The MetricsStore is obtained from ``context.extras["__metrics_store__"]``,
    following the standard IoC pattern used by all agent loop actions.  This
    ensures the action works with any storage backend (InMemory, Django ORM,
    etc.) without coupling to a specific database driver.

    Properties:
        days_to_analyze: Number of days to look back (default: 7)
        min_runs_for_analysis: Minimum runs needed to analyze a workflow (default: 3)
        min_continuations_for_proposal: Continuations of a workflow needed before
            proposing to extend it (default: 2)
        output_key: Where to store analysis (default: "metrics_analysis")

    Runs are goal runs, tool runs (``llm_agent`` tool calls, goal ``[tool] …``) or system
    runs (workflow tagged ``system`` in ``__workflow_library__``, when there is one). Only
    goal runs feed the goal statistics; tool and system runs are reported apart (#256).

    Output includes:
        - workflow_stats: Per-workflow statistics of goal runs (incl. continuation_rate)
        - low_performers: Workflows with success rate < 70%
        - high_performers: Workflows with success rate >= 90%
        - unrated_runs_count: Number of goal runs without user ratings
        - failure_patterns: Common failure reasons of goal runs
        - usage_trends: Workflow usage over time
        - recommendations: Initial recommendations based on metrics
        - continuation_analysis: Continuation chains, patterns and proposals (F136)
        - run_counts: Goal, tool and system runs, and expected tool misses
        - tool_workflow_stats: Per tool workflow: calls, successes, expected misses
          (``zebra_source.is_expected_miss``), real failures, success rate without misses
        - tool_failure_patterns: Failure reasons of tool runs, expected misses left out
        - system_workflow_stats: Per-workflow statistics of system runs

    Example workflow usage:
        ```yaml
        tasks:
          analyze_metrics:
            name: "Analyze Metrics"
            action: metrics_analyzer
            auto: true
            properties:
              days_to_analyze: 7
              output_key: metrics_analysis
        ```
    """

    description = "Analyze workflow performance metrics via the MetricsStore interface."

    inputs = [
        ParameterDef(
            name="days_to_analyze",
            type="int",
            description="Number of days to look back for analysis",
            required=False,
            default=7,
        ),
        ParameterDef(
            name="min_runs_for_analysis",
            type="int",
            description="Minimum runs needed to analyze a workflow",
            required=False,
            default=3,
        ),
        ParameterDef(
            name="min_continuations_for_proposal",
            type="int",
            description="Continuations of a workflow needed before proposing to extend it",
            required=False,
            default=2,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the analysis",
            required=False,
            default="metrics_analysis",
        ),
    ]

    outputs = [
        ParameterDef(
            name="analysis_period_days",
            type="int",
            description="Number of days analyzed",
            required=True,
        ),
        ParameterDef(
            name="total_runs_analyzed",
            type="int",
            description="Total number of workflow runs analyzed",
            required=True,
        ),
        ParameterDef(
            name="unique_workflows",
            type="int",
            description="Number of unique workflows",
            required=True,
        ),
        ParameterDef(
            name="workflow_stats",
            type="list[dict]",
            description="Per-workflow statistics",
            required=True,
        ),
        ParameterDef(
            name="low_performers",
            type="list[dict]",
            description="Workflows with success rate < 70%",
            required=True,
        ),
        ParameterDef(
            name="high_performers",
            type="list[dict]",
            description="Workflows with success rate >= 90%",
            required=True,
        ),
        ParameterDef(
            name="unrated_runs_count",
            type="int",
            description="Number of runs without user ratings",
            required=True,
        ),
        ParameterDef(
            name="failure_patterns",
            type="list[dict]",
            description="Common failure reasons grouped by workflow",
            required=True,
        ),
        ParameterDef(
            name="usage_trends",
            type="dict",
            description="Workflow usage trends over time",
            required=True,
        ),
        ParameterDef(
            name="recommendations",
            type="list[string]",
            description="Initial recommendations based on metrics",
            required=True,
        ),
        ParameterDef(
            name="continuation_analysis",
            type="dict",
            description=(
                "Continuation chains, frequently continued workflows, capability gaps, "
                "added steps and continuation-driven improvement proposals"
            ),
            required=True,
        ),
        ParameterDef(
            name="run_counts",
            type="dict",
            description="Number of goal, tool and system runs, and of expected tool misses",
            required=True,
        ),
        ParameterDef(
            name="tool_workflow_stats",
            type="list[dict]",
            description=(
                "Per tool workflow: calls, successes, expected misses, real failures and "
                "success rate over calls that were not expected misses"
            ),
            required=True,
        ),
        ParameterDef(
            name="tool_failure_patterns",
            type="list[dict]",
            description="Failure reasons of tool runs, expected misses left out",
            required=True,
        ),
        ParameterDef(
            name="system_workflow_stats",
            type="list[dict]",
            description="Per-workflow statistics of system workflow runs",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Analyze metrics from the MetricsStore."""
        metrics_store = context.extras.get("__metrics_store__")
        if metrics_store is None:
            return TaskResult.fail(
                "No metrics store available. Ensure __metrics_store__ is set in engine.extras."
            )

        days = task.properties.get("days_to_analyze", 7)
        min_runs = task.properties.get("min_runs_for_analysis", 3)
        min_continuations = task.properties.get("min_continuations_for_proposal", 2)
        output_key = task.properties.get("output_key", "metrics_analysis")

        try:
            system_workflows = await self._system_workflows(
                context.extras.get("__workflow_library__")
            )
            analysis = await self._analyze_metrics(
                metrics_store, days, min_runs, min_continuations, system_workflows
            )
            context.set_process_property(output_key, analysis)
            return TaskResult.ok(output=analysis)
        except Exception as e:
            return TaskResult.fail(f"Metrics analysis failed: {str(e)}")

    @staticmethod
    async def _system_workflows(library: Any) -> set[str]:
        """Names of the library's workflows tagged ``system``; none without a library."""
        if library is None:
            return set()
        try:
            return {w.name for w in await library.list_workflows() if SYSTEM_TAG in (w.tags or [])}
        except Exception as e:
            logger.warning("metrics_analyzer: could not list system workflows: %s", e)
            return set()

    async def _analyze_metrics(
        self,
        metrics_store: Any,
        days: int,
        min_runs: int,
        min_continuations: int = 2,
        system_workflows: set[str] | None = None,
    ) -> dict[str, Any]:
        """Perform the actual metrics analysis using the MetricsStore interface."""
        cutoff_date = datetime.now() - timedelta(days=days)

        # Fetch data via the abstract MetricsStore interface
        recent_runs = await metrics_store.get_runs_since(cutoff_date)
        all_stats = await metrics_store.get_all_stats()

        # Convert runs to dicts for downstream processing
        run_dicts = self._runs_to_dicts(recent_runs)
        by_kind: dict[str, list[dict]] = {GOAL_RUN: [], TOOL_RUN: [], SYSTEM_RUN: []}
        for r in run_dicts:
            by_kind[run_kind(r, system_workflows or set())].append(r)
        goal_runs = by_kind[GOAL_RUN]
        tool_runs = by_kind[TOOL_RUN]
        miss_ids = {r["id"] for r in tool_runs if not r["success"] and is_expected_miss(r["error"])}

        continuation_analysis = await self._gather_continuations(
            metrics_store, cutoff_date, min_continuations
        )
        continued_ids = set(continuation_analysis["continued_run_ids"])

        known_workflows = [stat.workflow_name for stat in all_stats]
        workflow_stats = self._workflow_stats(goal_runs, known_workflows, continued_ids)

        # Categorize workflows
        low_performers = [
            w for w in workflow_stats if w["success_rate"] < 0.7 and w["total_runs"] >= min_runs
        ]
        high_performers = [
            w for w in workflow_stats if w["success_rate"] >= 0.9 and w["total_runs"] >= min_runs
        ]

        # Get unrated runs
        unrated_runs = [r for r in goal_runs if r.get("user_rating") is None]

        # Analyze failure patterns
        failure_patterns = self._analyze_failures(goal_runs)

        # Calculate usage trends
        usage_trends = self._calculate_usage_trends(goal_runs)

        # Generate initial recommendations
        recommendations = self._generate_recommendations(
            workflow_stats, low_performers, failure_patterns, usage_trends
        )
        for fc in reversed(continuation_analysis["top_continued"][:3]):
            recommendations.insert(
                0,
                f"'{fc['workflow_name']}' was continued {fc['count']} times - "
                "review why users needed to carry on",
            )

        return {
            "analysis_period_days": days,
            "total_runs_analyzed": len(run_dicts),
            "unique_workflows": len(workflow_stats),
            "workflow_stats": workflow_stats,
            "low_performers": low_performers,
            "high_performers": high_performers,
            "unrated_runs_count": len(unrated_runs),
            "failure_patterns": failure_patterns,
            "usage_trends": usage_trends,
            "recommendations": recommendations,
            "continuation_analysis": continuation_analysis,
            "run_counts": {
                GOAL_RUN: len(goal_runs),
                TOOL_RUN: len(tool_runs),
                SYSTEM_RUN: len(by_kind[SYSTEM_RUN]),
                "expected_misses": len(miss_ids),
            },
            "tool_workflow_stats": self._tool_workflow_stats(tool_runs),
            "tool_failure_patterns": self._analyze_failures(
                [r for r in tool_runs if r["id"] not in miss_ids]
            ),
            "system_workflow_stats": self._workflow_stats(
                by_kind[SYSTEM_RUN], known_workflows, continued_ids
            ),
        }

    @staticmethod
    def _workflow_stats(
        runs: list[dict], known_workflows: list[str], continued_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Per-workflow statistics of ``runs`` for the store's known workflows, busiest first."""
        workflow_stats = []
        for name in known_workflows:
            period_runs = [r for r in runs if r["workflow_name"] == name]
            if not period_runs:
                continue
            total = len(period_runs)
            successful = sum(1 for r in period_runs if r["success"])
            ratings = [r["user_rating"] for r in period_runs if r["user_rating"] is not None]
            continued = sum(1 for r in period_runs if r["id"] in continued_ids)
            workflow_stats.append(
                {
                    "workflow_name": name,
                    "total_runs": total,
                    "successful_runs": successful,
                    "success_rate": successful / total,
                    "avg_rating": sum(ratings) / len(ratings) if ratings else None,
                    "avg_tokens": sum(r["tokens_used"] for r in period_runs) / total,
                    "last_used": max(r["started_at"] for r in period_runs),
                    "continued_runs": continued,
                    "continuation_rate": continued / total,
                }
            )
        workflow_stats.sort(key=lambda w: w["total_runs"], reverse=True)
        return workflow_stats

    @staticmethod
    def _tool_workflow_stats(runs: list[dict]) -> list[dict[str, Any]]:
        """Per tool workflow: calls, successes, expected misses and real failures (#256).

        The success rate leaves expected misses out: a miss is a correct answer, neither a
        success nor a failure of the tool. ``None`` when every call was a miss.
        """
        by_workflow: dict[str, list[dict]] = {}
        for r in runs:
            by_workflow.setdefault(r["workflow_name"], []).append(r)
        stats = []
        for name, calls in by_workflow.items():
            successful = sum(1 for r in calls if r["success"])
            misses = sum(1 for r in calls if not r["success"] and is_expected_miss(r["error"]))
            judged = len(calls) - misses
            stats.append(
                {
                    "workflow_name": name,
                    "total_runs": len(calls),
                    "successful_runs": successful,
                    "expected_misses": misses,
                    "failures": judged - successful,
                    "success_rate": successful / judged if judged else None,
                }
            )
        stats.sort(key=lambda w: w["total_runs"], reverse=True)
        return stats

    async def _gather_continuations(
        self, metrics_store: Any, cutoff: datetime, min_continuations: int
    ) -> dict[str, Any]:
        """Analyse continuation chains; never fail the wider analysis (F136)."""
        try:
            return await analyze_continuations(
                metrics_store, cutoff, min_continuations_for_proposal=min_continuations
            )
        except Exception as e:
            logger.warning("Continuation analysis skipped: %s", e)
            return empty_continuation_analysis()

    def _runs_to_dicts(self, runs: list) -> list[dict[str, Any]]:
        """Convert WorkflowRun dataclass instances to plain dicts."""
        results = []
        for run in runs:
            started_at_str = (
                run.started_at.isoformat()
                if hasattr(run.started_at, "isoformat")
                else str(run.started_at)
            )
            results.append(
                {
                    "id": run.id,
                    "workflow_name": run.workflow_name,
                    "goal": run.goal,
                    "started_at": started_at_str,
                    "completed_at": (
                        run.completed_at.isoformat()
                        if run.completed_at and hasattr(run.completed_at, "isoformat")
                        else str(run.completed_at)
                        if run.completed_at
                        else None
                    ),
                    "success": run.success,
                    "user_rating": run.user_rating,
                    "tokens_used": run.tokens_used or 0,
                    "error": run.error,
                }
            )
        return results

    def _analyze_failures(self, runs: list[dict]) -> list[dict[str, Any]]:
        """Analyze failure patterns."""
        failures = [r for r in runs if not r["success"]]
        if not failures:
            return []

        # Group by workflow
        by_workflow: dict[str, list] = {}
        for f in failures:
            wf = f["workflow_name"]
            if wf not in by_workflow:
                by_workflow[wf] = []
            by_workflow[wf].append(f)

        # Find common error patterns
        patterns = []
        for workflow, workflow_failures in by_workflow.items():
            error_types: dict[str, int] = {}
            for f in workflow_failures:
                error = f.get("error", "Unknown error")
                # Extract error type (first line or first 50 chars)
                error_key = error.split("\n")[0][:50] if error else "Unknown"
                error_types[error_key] = error_types.get(error_key, 0) + 1

            patterns.append(
                {
                    "workflow_name": workflow,
                    "failure_count": len(workflow_failures),
                    "error_types": error_types,
                    "sample_goals": [f["goal"][:100] for f in workflow_failures[:3]],
                }
            )

        # Sort by failure count
        patterns.sort(key=lambda x: x["failure_count"], reverse=True)
        return patterns

    def _calculate_usage_trends(self, runs: list[dict]) -> dict[str, Any]:
        """Calculate usage trends over time."""
        if not runs:
            return {"daily_counts": {}, "most_used": [], "growing": [], "declining": []}

        # Group by day
        daily: dict[str, int] = {}
        workflow_daily: dict[str, dict[str, int]] = {}

        for run in runs:
            date = run["started_at"][:10]  # YYYY-MM-DD
            daily[date] = daily.get(date, 0) + 1

            wf = run["workflow_name"]
            if wf not in workflow_daily:
                workflow_daily[wf] = {}
            workflow_daily[wf][date] = workflow_daily[wf].get(date, 0) + 1

        # Calculate workflow totals
        workflow_totals = {wf: sum(counts.values()) for wf, counts in workflow_daily.items()}

        # Sort by usage
        most_used = sorted(workflow_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "daily_counts": daily,
            "most_used": [{"workflow": wf, "count": c} for wf, c in most_used],
        }

    def _generate_recommendations(
        self,
        workflow_stats: list[dict],
        low_performers: list[dict],
        failure_patterns: list[dict],
        usage_trends: dict,
    ) -> list[str]:
        """Generate initial recommendations based on metrics."""
        recommendations = []

        # Low performer recommendations
        for lp in low_performers[:3]:
            name = lp["workflow_name"]
            rate = lp["success_rate"] * 100
            recommendations.append(
                f"Review '{name}' - only {rate:.0f}% success rate over {lp['total_runs']} runs"
            )

        # Failure pattern recommendations
        for fp in failure_patterns[:2]:
            name = fp["workflow_name"]
            count = fp["failure_count"]
            recommendations.append(f"Investigate failures in '{name}' - {count} failures detected")

        # High usage low rating
        for ws in workflow_stats:
            if ws["total_runs"] >= 5 and ws["avg_rating"] is not None and ws["avg_rating"] < 3.0:
                recommendations.append(
                    f"Improve '{ws['workflow_name']}' - avg rating {ws['avg_rating']:.1f}/5"
                )

        if not recommendations:
            recommendations.append(
                "All workflows performing well - consider adding new capabilities"
            )

        return recommendations

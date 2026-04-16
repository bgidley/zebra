"""MetricsAnalyzerAction - Analyze workflow performance metrics.

Uses the MetricsStore interface from engine.extras to query run data,
ensuring compatibility with all storage backends (InMemory, Django ORM, etc.).
"""

from datetime import datetime, timedelta
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction


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
        output_key: Where to store analysis (default: "metrics_analysis")

    Output includes:
        - workflow_stats: Per-workflow statistics
        - low_performers: Workflows with success rate < 70%
        - high_performers: Workflows with success rate >= 90%
        - unrated_runs_count: Number of runs without user ratings
        - failure_patterns: Common failure reasons
        - usage_trends: Workflow usage over time
        - recommendations: Initial recommendations based on metrics

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
        output_key = task.properties.get("output_key", "metrics_analysis")

        try:
            analysis = await self._analyze_metrics(metrics_store, days, min_runs)
            context.set_process_property(output_key, analysis)
            return TaskResult.ok(output=analysis)
        except Exception as e:
            return TaskResult.fail(f"Metrics analysis failed: {str(e)}")

    async def _analyze_metrics(
        self, metrics_store: Any, days: int, min_runs: int
    ) -> dict[str, Any]:
        """Perform the actual metrics analysis using the MetricsStore interface."""
        cutoff_date = datetime.now() - timedelta(days=days)

        # Fetch data via the abstract MetricsStore interface
        recent_runs = await metrics_store.get_runs_since(cutoff_date)
        all_stats = await metrics_store.get_all_stats()

        # Convert runs to dicts for downstream processing
        run_dicts = self._runs_to_dicts(recent_runs)

        # Build per-workflow stats from the all_stats response,
        # filtered to only workflows active in the analysis period
        active_workflow_names = {r["workflow_name"] for r in run_dicts}
        workflow_stats = []
        for stat in all_stats:
            if stat.workflow_name in active_workflow_names:
                # Recalculate stats from the recent runs for the analysis period
                period_runs = [r for r in run_dicts if r["workflow_name"] == stat.workflow_name]
                total = len(period_runs)
                successful = sum(1 for r in period_runs if r["success"])
                ratings = [r["user_rating"] for r in period_runs if r["user_rating"] is not None]
                avg_rating = sum(ratings) / len(ratings) if ratings else None
                avg_tokens = sum(r["tokens_used"] for r in period_runs) / total if total > 0 else 0
                last_used = max(r["started_at"] for r in period_runs) if period_runs else None

                workflow_stats.append(
                    {
                        "workflow_name": stat.workflow_name,
                        "total_runs": total,
                        "successful_runs": successful,
                        "success_rate": successful / total if total > 0 else 0,
                        "avg_rating": avg_rating,
                        "avg_tokens": avg_tokens,
                        "last_used": last_used,
                    }
                )

        # Sort by total_runs descending
        workflow_stats.sort(key=lambda w: w["total_runs"], reverse=True)

        # Categorize workflows
        low_performers = [
            w for w in workflow_stats if w["success_rate"] < 0.7 and w["total_runs"] >= min_runs
        ]
        high_performers = [
            w for w in workflow_stats if w["success_rate"] >= 0.9 and w["total_runs"] >= min_runs
        ]

        # Get unrated runs
        unrated_runs = [r for r in run_dicts if r.get("user_rating") is None]

        # Analyze failure patterns
        failure_patterns = self._analyze_failures(run_dicts)

        # Calculate usage trends
        usage_trends = self._calculate_usage_trends(run_dicts)

        # Generate initial recommendations
        recommendations = self._generate_recommendations(
            workflow_stats, low_performers, failure_patterns, usage_trends
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
        }

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

"""MetricsAnalyzerAction - Analyze workflow performance metrics."""

from datetime import datetime, timedelta
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction


class MetricsAnalyzerAction(TaskAction):
    """
    Analyze workflow performance metrics from the database.

    This action reads metrics data and produces analysis that can be used
    by the agent to identify improvement opportunities.

    Properties:
        metrics_db_path: Path to the metrics SQLite database
        days_to_analyze: Number of days to look back (default: 7)
        min_runs_for_analysis: Minimum runs needed to analyze a workflow (default: 3)
        output_key: Where to store analysis (default: "metrics_analysis")

    Output includes:
        - workflow_stats: Per-workflow statistics
        - low_performers: Workflows with success rate < 70%
        - high_performers: Workflows with success rate >= 90%
        - unrated_runs: Recent runs without user ratings
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
              metrics_db_path: "{{metrics_db}}"
              days_to_analyze: 7
              output_key: metrics_analysis
        ```
    """

    description = "Analyze workflow performance metrics from a SQLite database."

    inputs = [
        ParameterDef(
            name="metrics_db_path",
            type="string",
            description="Path to the metrics SQLite database",
            required=False,
        ),
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
        """Analyze metrics from the database."""

        db_path = task.properties.get("metrics_db_path")
        if not db_path:
            # Try to get from process properties
            db_path = context.process.properties.get("__metrics_db_path__")

        if not db_path:
            return TaskResult.fail("No metrics_db_path provided")

        days = task.properties.get("days_to_analyze", 7)
        min_runs = task.properties.get("min_runs_for_analysis", 3)
        output_key = task.properties.get("output_key", "metrics_analysis")

        try:
            analysis = await self._analyze_metrics(db_path, days, min_runs)

            # Store in process properties
            context.set_process_property(output_key, analysis)

            return TaskResult.ok(output=analysis)

        except Exception as e:
            return TaskResult.fail(f"Metrics analysis failed: {str(e)}")

    async def _analyze_metrics(self, db_path: str, days: int, min_runs: int) -> dict[str, Any]:
        """Perform the actual metrics analysis."""
        import aiosqlite

        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.isoformat()

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get workflow statistics
            workflow_stats = await self._get_workflow_stats(db, cutoff_str, min_runs)

            # Get recent runs for pattern analysis
            recent_runs = await self._get_recent_runs(db, cutoff_str)

            # Categorize workflows
            low_performers = [
                w for w in workflow_stats if w["success_rate"] < 0.7 and w["total_runs"] >= min_runs
            ]
            high_performers = [
                w
                for w in workflow_stats
                if w["success_rate"] >= 0.9 and w["total_runs"] >= min_runs
            ]

            # Get unrated runs
            unrated_runs = [r for r in recent_runs if r.get("user_rating") is None]

            # Analyze failure patterns
            failure_patterns = self._analyze_failures(recent_runs)

            # Calculate usage trends
            usage_trends = self._calculate_usage_trends(recent_runs)

            # Generate initial recommendations
            recommendations = self._generate_recommendations(
                workflow_stats, low_performers, failure_patterns, usage_trends
            )

            return {
                "analysis_period_days": days,
                "total_runs_analyzed": len(recent_runs),
                "unique_workflows": len(workflow_stats),
                "workflow_stats": workflow_stats,
                "low_performers": low_performers,
                "high_performers": high_performers,
                "unrated_runs_count": len(unrated_runs),
                "failure_patterns": failure_patterns,
                "usage_trends": usage_trends,
                "recommendations": recommendations,
            }

    async def _get_workflow_stats(self, db, cutoff_str: str, min_runs: int) -> list[dict[str, Any]]:
        """Get statistics for each workflow."""
        query = """
            SELECT
                workflow_name,
                COUNT(*) as total_runs,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_runs,
                AVG(CASE WHEN user_rating IS NOT NULL THEN user_rating END) as avg_rating,
                AVG(tokens_used) as avg_tokens,
                MAX(started_at) as last_used
            FROM workflow_runs
            WHERE started_at >= ?
            GROUP BY workflow_name
            ORDER BY total_runs DESC
        """

        results = []
        async with db.execute(query, (cutoff_str,)) as cursor:
            async for row in cursor:
                total = row["total_runs"]
                successful = row["successful_runs"]
                results.append(
                    {
                        "workflow_name": row["workflow_name"],
                        "total_runs": total,
                        "successful_runs": successful,
                        "success_rate": successful / total if total > 0 else 0,
                        "avg_rating": row["avg_rating"],
                        "avg_tokens": row["avg_tokens"],
                        "last_used": row["last_used"],
                    }
                )

        return results

    async def _get_recent_runs(self, db, cutoff_str: str) -> list[dict[str, Any]]:
        """Get recent workflow runs."""
        query = """
            SELECT
                id, workflow_name, goal, started_at, completed_at,
                success, user_rating, tokens_used, error
            FROM workflow_runs
            WHERE started_at >= ?
            ORDER BY started_at DESC
        """

        results = []
        async with db.execute(query, (cutoff_str,)) as cursor:
            async for row in cursor:
                results.append(
                    {
                        "id": row["id"],
                        "workflow_name": row["workflow_name"],
                        "goal": row["goal"],
                        "started_at": row["started_at"],
                        "completed_at": row["completed_at"],
                        "success": bool(row["success"]),
                        "user_rating": row["user_rating"],
                        "tokens_used": row["tokens_used"],
                        "error": row["error"],
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

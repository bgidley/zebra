"""Web views for Zebra Agent UI using Django templates + HTMX.

This module provides async HTML views for the agent-focused web interface.
All URLs are simplified since this is an agent-only application:
- / -> Dashboard
- /run/ -> Run Goal
- /workflows/ -> Workflow Library
- /runs/ -> Run History
"""

import logging

from asgiref.sync import sync_to_async
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from zebra_agent_web.api import agent_engine

logger = logging.getLogger(__name__)


# =============================================================================
# Dashboard
# =============================================================================


async def dashboard(request):
    """Agent dashboard with overview of workflows and recent activity."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()
    metrics = agent_engine.get_metrics()

    workflows = await library.list_workflows()
    all_stats = await metrics.get_all_stats()
    recent_runs = await metrics.get_recent_runs(limit=10)

    # Calculate aggregate stats
    total_runs = sum(s.total_runs for s in all_stats)
    successful_runs = sum(s.successful_runs for s in all_stats)
    success_rate = successful_runs / total_runs if total_runs > 0 else 0

    context = {
        "workflows_count": len(workflows),
        "total_runs": total_runs,
        "success_rate": f"{success_rate:.0%}",
        "recent_runs": [
            {
                "id": r.id,
                "workflow_name": r.workflow_name,
                "goal": r.goal[:80] + "..." if len(r.goal) > 80 else r.goal,
                "success": r.success,
                "started_at": r.started_at,
                "tokens_used": r.tokens_used,
            }
            for r in recent_runs
        ],
        "top_workflows": [
            {
                "name": w.name,
                "description": w.description[:60] + "..."
                if len(w.description) > 60
                else w.description,
                "use_count": w.use_count,
                "success_rate": f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A",
            }
            for w in workflows[:5]
        ],
    }

    return render(request, "pages/dashboard.html", context)


# =============================================================================
# Workflow Library
# =============================================================================


async def workflow_library(request):
    """List all workflows in the library."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()

    workflows = await library.list_workflows()

    workflows_data = [
        {
            "name": w.name,
            "description": w.description,
            "tags": w.tags,
            "version": w.version,
            "use_count": w.use_count,
            "success_rate": f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A",
        }
        for w in workflows
    ]

    context = {"workflows": workflows_data}

    if request.headers.get("HX-Request"):
        return render(request, "partials/workflow_library_list.html", context)
    return render(request, "pages/workflow_library.html", context)


async def workflow_detail(request, workflow_name):
    """View a specific workflow's YAML and stats."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()
    metrics = agent_engine.get_metrics()

    try:
        yaml_content = library.get_workflow_yaml(workflow_name)
        stats = await metrics.get_stats(workflow_name)
        workflows = await library.list_workflows()
        workflow_info = next((w for w in workflows if w.name == workflow_name), None)
    except ValueError:
        return HttpResponse("Workflow not found", status=404)

    context = {
        "workflow_name": workflow_name,
        "yaml_content": yaml_content,
        "description": workflow_info.description if workflow_info else "",
        "tags": workflow_info.tags if workflow_info else [],
        "stats": {
            "total_runs": stats.total_runs,
            "successful_runs": stats.successful_runs,
            "success_rate": f"{stats.success_rate:.0%}" if stats.total_runs > 0 else "N/A",
            "avg_rating": f"{stats.avg_rating:.1f}" if stats.avg_rating else "N/A",
            "last_used": stats.last_used.strftime("%Y-%m-%d %H:%M") if stats.last_used else "Never",
        },
    }

    return render(request, "pages/workflow_detail.html", context)


@require_http_methods(["POST"])
async def workflow_create(request):
    """Create a new workflow from YAML."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()

    yaml_content = request.POST.get("yaml_content", "")
    if not yaml_content.strip():
        return HttpResponse("YAML content required", status=400)

    try:
        workflow_name = library.add_workflow(yaml_content)

        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = f"/workflows/{workflow_name}/"
            return response
        return redirect("workflow_detail", workflow_name=workflow_name)
    except Exception as e:
        logger.exception("Failed to create workflow")
        return HttpResponse(f"Error: {e}", status=400)


@require_http_methods(["DELETE"])
async def workflow_delete(request, workflow_name):
    """Delete a workflow from the library."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()

    try:
        import yaml

        # File operations need sync_to_async
        @sync_to_async
        def delete_workflow_file():
            for yaml_file in library.library_path.glob("*.yaml"):
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if data and data.get("name") == workflow_name:
                    yaml_file.unlink()
                    if workflow_name in library._cache:
                        del library._cache[workflow_name]
                    return True
            return False

        await delete_workflow_file()

        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = "/workflows/"
            return response
        return redirect("workflow_library")
    except Exception as e:
        logger.exception("Failed to delete workflow")
        return HttpResponse(f"Error: {e}", status=400)


# =============================================================================
# Run Goal
# =============================================================================


async def run_goal_form(request):
    """Display the form to run a goal."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()

    workflows = await library.list_workflows()

    context = {
        "workflows": [
            {
                "name": w.name,
                "description": w.description,
                "tags": w.tags,
                "success_rate": f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A",
            }
            for w in workflows
        ],
    }

    return render(request, "pages/run_goal.html", context)


def _format_output(output):
    """Format output for display - handles dicts, lists, and strings."""
    import json

    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, (dict, list)):
        return json.dumps(output, indent=2, ensure_ascii=False)
    return str(output)


@require_http_methods(["POST"])
async def run_goal_execute(request):
    """Execute a goal using the agent loop."""
    await agent_engine.ensure_initialized()
    agent_loop = agent_engine.get_agent_loop()

    goal = request.POST.get("goal", "").strip()
    if not goal:
        return HttpResponse("Goal is required", status=400)

    try:
        result = await agent_loop.process_goal(goal)

        context = {
            "result": {
                "run_id": result.run_id,
                "workflow_name": result.workflow_name,
                "goal": result.goal,
                "success": result.success,
                "output": _format_output(result.output),
                "error": result.error,
                "tokens_used": result.tokens_used,
                "created_new_workflow": result.created_new_workflow,
            }
        }

        if request.headers.get("HX-Request"):
            return render(request, "partials/goal_result.html", context)
        return render(request, "pages/goal_result.html", context)
    except Exception as e:
        logger.exception("Failed to execute goal")
        if request.headers.get("HX-Request"):
            return render(request, "partials/goal_error.html", {"error": str(e)})
        return HttpResponse(f"Error: {e}", status=500)


async def run_detail(request, run_id):
    """View details of a specific run."""
    await agent_engine.ensure_initialized()
    metrics = agent_engine.get_metrics()

    run = await metrics.get_run(run_id)
    if not run:
        return HttpResponse("Run not found", status=404)

    context = {
        "run": {
            "id": run.id,
            "workflow_name": run.workflow_name,
            "goal": run.goal,
            "success": run.success,
            "output": _format_output(run.output),
            "error": run.error,
            "tokens_used": run.tokens_used,
            "user_rating": run.user_rating,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }
    }

    return render(request, "pages/run_detail.html", context)


@require_http_methods(["POST"])
async def run_rate(request, run_id):
    """Rate a run."""
    await agent_engine.ensure_initialized()
    agent_loop = agent_engine.get_agent_loop()

    rating = request.POST.get("rating")
    if not rating:
        return HttpResponse("Rating is required", status=400)

    try:
        rating = int(rating)
        await agent_loop.record_rating(run_id, rating)

        if request.headers.get("HX-Request"):
            return HttpResponse(f'<span class="text-green-400">Rated {rating}/5</span>')
        return redirect("run_detail", run_id=run_id)
    except ValueError:
        return HttpResponse("Invalid rating", status=400)
    except Exception as e:
        logger.exception("Failed to rate run")
        return HttpResponse(f"Error: {e}", status=400)


# =============================================================================
# Recent Runs
# =============================================================================


async def recent_runs(request):
    """List recent runs."""
    await agent_engine.ensure_initialized()
    metrics = agent_engine.get_metrics()

    limit = int(request.GET.get("limit", 20))
    runs = await metrics.get_recent_runs(limit=limit)

    runs_data = [
        {
            "id": r.id,
            "workflow_name": r.workflow_name,
            "goal": r.goal[:80] + "..." if len(r.goal) > 80 else r.goal,
            "success": r.success,
            "started_at": r.started_at,
            "tokens_used": r.tokens_used,
            "user_rating": r.user_rating,
        }
        for r in runs
    ]

    context = {"runs": runs_data}

    if request.headers.get("HX-Request"):
        return render(request, "partials/recent_runs_list.html", context)
    return render(request, "pages/recent_runs.html", context)

"""Web views for Zebra Agent UI using Django templates + HTMX.

This module provides async HTML views for the agent-focused web interface.
All URLs are simplified since this is an agent-only application:
- / -> Dashboard
- /run/ -> Run Goal
- /workflows/ -> Workflow Library
- /runs/ -> Run History
- /tasks/ -> Pending Human Tasks
"""

import asyncio
import logging
import uuid
from typing import Any

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from zebra_agent_web.api import agent_engine, engine

logger = logging.getLogger(__name__)

# Track active background tasks for status checks
_active_tasks: dict[str, asyncio.Task] = {}


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
    """Format output for display.

    Workflows with `result_key` set will have their output already as a plain
    string. For any remaining dict/list values (legacy runs or workflows without
    result_key) fall back to a JSON dump.

    For string output, tries to parse it as JSON first (runs store JSON),
    then falls back to the raw string.
    """
    import json

    if output is None:
        return ""

    # Normalise: if we received a string, try to parse it as JSON
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
            if isinstance(parsed, (dict, list)):
                output = parsed
            else:
                return output  # plain string after JSON parse → return as-is
        except (json.JSONDecodeError, ValueError):
            return output  # plain/repr string → return as-is

    if isinstance(output, (dict, list)):
        return json.dumps(output, indent=2, ensure_ascii=False)

    return str(output)


@require_http_methods(["POST"])
async def run_goal_execute(request):
    """Start goal execution in background and return processing UI immediately.

    The actual workflow execution happens in a background task, with progress
    updates streamed via WebSocket to the client.
    """
    goal = request.POST.get("goal", "").strip()
    if not goal:
        return HttpResponse("Goal is required", status=400)

    # Generate run ID upfront so client can connect to WebSocket
    run_id = str(uuid.uuid4())

    # Start background task for goal execution
    task = asyncio.create_task(_execute_goal_background(run_id, goal))
    _active_tasks[run_id] = task

    # Add cleanup callback
    task.add_done_callback(lambda t: _active_tasks.pop(run_id, None))

    # Return processing UI immediately
    context = {"run_id": run_id, "goal": goal}

    if request.headers.get("HX-Request"):
        return render(request, "partials/goal_processing.html", context)
    return render(request, "pages/goal_processing.html", context)


async def _execute_goal_background(run_id: str, goal: str) -> None:
    """Execute goal in background, sending progress via WebSocket channel layer.

    This function runs as an asyncio task, independent of the HTTP request.
    Progress updates are sent to the channel group for the run_id, where
    connected WebSocket clients receive them.
    """
    channel_layer = get_channel_layer()
    group_name = f"goal_{run_id}"

    async def progress_callback(event: str, data: dict[str, Any]) -> None:
        """Send progress update to WebSocket clients."""
        await channel_layer.group_send(
            group_name,
            {
                "type": "goal.progress",
                "data": {"event": event, "run_id": run_id, **data},
            },
        )

    try:
        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()

        result = await agent_loop.process_goal(
            goal,
            progress_callback=progress_callback,
            run_id=run_id,
        )

        # Send completion event
        if result.success:
            await progress_callback(
                "completed",
                {
                    "workflow_name": result.workflow_name,
                    "success": True,
                    "output": _format_output(result.output),
                    "tokens_used": result.tokens_used,
                    "created_new_workflow": result.created_new_workflow,
                },
            )
        else:
            await progress_callback(
                "failed",
                {
                    "workflow_name": result.workflow_name,
                    "error": result.error,
                },
            )

    except Exception as e:
        logger.exception(f"Background goal execution failed for {run_id}")
        await progress_callback("failed", {"error": str(e)})


def is_task_active(run_id: str) -> bool:
    """Check if a background task is still running for a given run ID."""
    return run_id in _active_tasks


async def run_detail(request, run_id):
    """View details of a specific run."""
    await agent_engine.ensure_initialized()
    metrics = agent_engine.get_metrics()
    library = agent_engine.get_library()

    run = await metrics.get_run(run_id)
    if not run:
        return HttpResponse("Run not found", status=404)

    # Load task executions for this run
    task_executions = await metrics.get_task_executions(run_id)

    # Load workflow definition for diagram
    workflow_svg = None
    workflow_definition = None
    if run.workflow_name:
        try:
            workflow_definition = library.get_workflow(run.workflow_name)

            # Generate SVG diagram
            from zebra_agent_web.diagram import generate_workflow_svg

            workflow_svg = generate_workflow_svg(workflow_definition, task_executions)
        except ValueError:
            # Workflow not found in library (may have been deleted)
            pass

    # Format task executions for template
    formatted_executions = []
    for exec in task_executions:
        # Get task definition properties if available
        task_props = {}
        if workflow_definition and exec.task_definition_id in workflow_definition.tasks:
            task_def = workflow_definition.tasks[exec.task_definition_id]
            task_props = task_def.properties

        # Calculate duration
        duration = None
        if exec.started_at and exec.completed_at:
            delta = exec.completed_at - exec.started_at
            duration = f"{delta.total_seconds():.2f}s"

        formatted_executions.append(
            {
                "id": exec.id,
                "task_id": exec.task_definition_id,
                "task_name": exec.task_name,
                "execution_order": exec.execution_order,
                "state": exec.state,
                "started_at": exec.started_at,
                "completed_at": exec.completed_at,
                "duration": duration,
                "output": _format_output(exec.output),
                "error": exec.error,
                "properties": task_props,
            }
        )

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
        },
        "workflow_svg": workflow_svg,
        "task_executions": formatted_executions,
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


@require_http_methods(["POST"])
async def run_feedback(request, run_id):
    """Save free-text feedback for a run into workflow memory."""
    await agent_engine.ensure_initialized()
    agent_loop = agent_engine.get_agent_loop()

    feedback = request.POST.get("feedback", "").strip()
    if not feedback:
        return HttpResponse("Feedback is required", status=400)

    try:
        found = await agent_loop.record_feedback(run_id, feedback)
        if request.headers.get("HX-Request"):
            if found:
                return HttpResponse(
                    '<span class="text-green-400">Feedback saved — it will be '
                    "used to improve future runs of this workflow.</span>"
                )
            return HttpResponse(
                '<span class="text-amber-300">Feedback saved, but no matching '
                "memory entry was found (the run may still be processing).</span>"
            )
        return redirect("run_detail", run_id=run_id)
    except Exception as e:
        logger.exception("Failed to save feedback for run %s", run_id)
        return HttpResponse(f"Error: {e}", status=400)


# =============================================================================
# Activity (unified view: in-progress runs, pending tasks, completed runs)
# =============================================================================


async def activity(request):
    """Unified activity page showing goals grouped with their tasks.

    Combines the old "In Progress", "Pending Tasks", and "History" pages into
    a single grouped view. Each running goal is shown as a card with its
    pending tasks nested underneath.

    Query params:
        human_only: "true" (default) to show only manual tasks, "false" for all
        show_completed: "true" to include completed goals, "false" (default)
    """
    human_only = request.GET.get("human_only", "true") == "true"
    show_completed = request.GET.get("show_completed", "false") == "true"

    await agent_engine.ensure_initialized()
    await engine.ensure_initialized()

    metrics = agent_engine.get_metrics()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    # Fetch in-progress runs (from agent metrics)
    in_progress = await metrics.get_in_progress_runs()

    # Fetch all running processes (from engine state)
    running_processes = await store.get_running_processes()
    # Build run_id -> processes mapping from process properties
    # A run may have multiple processes (main + sub-processes)
    run_id_to_processes: dict[str, list] = {}
    orphan_processes = []
    for process in running_processes:
        props = process.properties or {}
        run_id = props.get("run_id")
        if run_id:
            run_id_to_processes.setdefault(run_id, []).append(process)
        else:
            # Check if this is a sub-process whose parent has a run_id
            if process.parent_process_id:
                # Try to find the parent's run_id
                parent = await store.load_process(process.parent_process_id)
                if parent:
                    parent_run_id = (parent.properties or {}).get("run_id")
                    if parent_run_id:
                        run_id_to_processes.setdefault(parent_run_id, []).append(process)
                        continue
            orphan_processes.append(process)

    # Build activity groups for in-progress runs
    activity_groups = []
    in_progress_run_ids = {run.id for run in in_progress}
    for run in in_progress:
        processes = run_id_to_processes.get(run.id, [])
        tasks_data = await _get_tasks_for_processes(processes, store, wf_engine, human_only)

        activity_groups.append(
            {
                "run_id": run.id,
                "goal": run.goal[:120] + "..." if len(run.goal) > 120 else run.goal,
                "workflow_name": run.workflow_name,
                "started_at": run.started_at,
                "completed_at": None,
                "success": None,
                "tokens_used": run.tokens_used,
                "user_rating": None,
                "is_running": True,
                "tasks": tasks_data,
                "has_human_tasks": any(t["is_human"] for t in tasks_data),
            }
        )

    # Handle running processes whose run_id has no matching metrics entry.
    # This happens when the agent metrics record was lost/completed but the
    # engine processes are still running (e.g. server restart, stale state).
    for run_id, processes in run_id_to_processes.items():
        if run_id in in_progress_run_ids:
            continue
        tasks_data = await _get_tasks_for_processes(processes, store, wf_engine, human_only)
        if not tasks_data:
            continue
        earliest = min((p.created_at for p in processes), default=None)
        activity_groups.append(
            {
                "run_id": run_id,
                "goal": f"Run {run_id[:8]}…",
                "workflow_name": None,
                "started_at": earliest,
                "completed_at": None,
                "success": None,
                "tokens_used": 0,
                "user_rating": None,
                "is_running": True,
                "tasks": tasks_data,
                "has_human_tasks": any(t["is_human"] for t in tasks_data),
            }
        )

    # Handle orphan processes (not linked to any run)
    if orphan_processes:
        orphan_tasks = await _get_tasks_for_processes(
            orphan_processes, store, wf_engine, human_only
        )
        if orphan_tasks:
            activity_groups.append(
                {
                    "run_id": None,
                    "goal": "Tasks from other processes",
                    "workflow_name": None,
                    "started_at": orphan_processes[0].created_at,
                    "completed_at": None,
                    "success": None,
                    "tokens_used": 0,
                    "user_rating": None,
                    "is_running": True,
                    "tasks": orphan_tasks,
                    "has_human_tasks": any(t["is_human"] for t in orphan_tasks),
                }
            )

    # Surface READY human tasks whose process has already completed.
    # This happens when the agent loop finishes but a human task is still pending
    # (e.g. the workflow created a human task as its final step).
    already_shown_process_ids = {t["process_id"] for g in activity_groups for t in g["tasks"]}
    all_ready_tasks = await store.get_ready_tasks()
    logger.debug(
        "activity: all_ready_tasks=%s",
        [(t.id, t.task_definition_id, t.process_id) for t in all_ready_tasks],
    )
    for ready_task in all_ready_tasks:
        if ready_task.process_id in already_shown_process_ids:
            continue
        process = await store.load_process(ready_task.process_id)
        if not process:
            continue
        definition = await store.load_definition(process.definition_id)
        if not definition:
            continue
        task_def = definition.tasks.get(ready_task.task_definition_id)
        if not task_def:
            continue
        is_human = not task_def.auto
        if human_only and not is_human:
            continue
        schema = task_def.properties.get("schema", {})
        # Try to recover goal/run context from process properties
        proc_props = process.properties or {}
        run_id = proc_props.get("run_id")
        goal = proc_props.get("goal", "")
        workflow_name = proc_props.get("workflow_name")
        # Walk up to parent if needed
        if not run_id and process.parent_process_id:
            parent = await store.load_process(process.parent_process_id)
            if parent:
                parent_props = parent.properties or {}
                run_id = parent_props.get("run_id")
                if not goal:
                    goal = parent_props.get("goal", "")
                if not workflow_name:
                    workflow_name = parent_props.get("workflow_name")
        task_data = {
            "id": ready_task.id,
            "task_definition_id": ready_task.task_definition_id,
            "task_name": task_def.name,
            "process_id": ready_task.process_id,
            "process_name": definition.name,
            "created_at": ready_task.created_at,
            "schema_title": schema.get("title", ""),
            "is_human": is_human,
        }
        # Find or create a group for this run_id
        existing = next((g for g in activity_groups if g["run_id"] == run_id), None)
        if existing:
            existing["tasks"].append(task_data)
            if is_human:
                existing["has_human_tasks"] = True
        else:
            activity_groups.append(
                {
                    "run_id": run_id,
                    "goal": goal[:120] + "..." if len(goal) > 120 else goal,
                    "workflow_name": workflow_name,
                    "started_at": process.created_at,
                    "completed_at": process.completed_at,
                    "success": None,
                    "tokens_used": 0,
                    "user_rating": None,
                    "is_running": False,
                    "tasks": [task_data],
                    "has_human_tasks": is_human,
                }
            )
        already_shown_process_ids.add(ready_task.process_id)

    # Optionally include completed runs
    if show_completed:
        completed_runs = await metrics.get_completed_runs(limit=20)
        for run in completed_runs:
            activity_groups.append(
                {
                    "run_id": run.id,
                    "goal": run.goal[:120] + "..." if len(run.goal) > 120 else run.goal,
                    "workflow_name": run.workflow_name,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "success": run.success,
                    "tokens_used": run.tokens_used,
                    "user_rating": run.user_rating,
                    "is_running": False,
                    "tasks": [],
                    "has_human_tasks": False,
                }
            )

    has_running = any(g["is_running"] for g in activity_groups)

    context = {
        "groups": activity_groups,
        "human_only": human_only,
        "show_completed": show_completed,
        "has_running": has_running,
    }

    if request.headers.get("HX-Request"):
        return render(request, "partials/activity_list.html", context)
    return render(request, "pages/activity.html", context)


async def _get_tasks_for_processes(
    processes: list,
    store,
    wf_engine,
    human_only: bool,
) -> list[dict]:
    """Get pending tasks for a list of processes, with definition metadata."""
    tasks_data = []
    for process in processes:
        pending = await wf_engine.get_pending_tasks(process.id)
        if not pending:
            continue

        definition = await store.load_definition(process.definition_id)
        if not definition:
            continue

        for task in pending:
            task_def = definition.tasks.get(task.task_definition_id)
            if not task_def:
                continue

            is_human = not task_def.auto
            if human_only and not is_human:
                continue

            schema = task_def.properties.get("schema", {})
            tasks_data.append(
                {
                    "id": task.id,
                    "task_definition_id": task.task_definition_id,
                    "task_name": task_def.name,
                    "process_id": process.id,
                    "process_name": definition.name,
                    "created_at": task.created_at,
                    "schema_title": schema.get("title", ""),
                    "is_human": is_human,
                }
            )

    return tasks_data


# Legacy URL redirects for backward compatibility
async def recent_runs(request):
    """Redirect to activity page with completed filter."""
    return redirect("/activity/?show_completed=true")


async def in_progress_runs(request):
    """Redirect to activity page."""
    return redirect("/activity/")


async def pending_tasks(request):
    """Redirect to activity page with human tasks filter."""
    return redirect("/activity/?human_only=true")


# =============================================================================
# Human Tasks
# =============================================================================


def _resolve_schema_defaults(schema: dict, process_properties: dict) -> dict:
    """Resolve {{template}} variables in schema field default values.

    When a task schema uses {{var}} as a default (e.g. to pre-populate a
    read-only field with output from a previous task), those references must
    be resolved against the process properties before the form is rendered.
    Only string defaults are resolved; other types are left unchanged.
    """
    import copy
    import re

    def _resolve(value: str) -> str:
        def replace_var(match: re.Match) -> str:
            var = match.group(1)
            if "." in var:
                task_id, attr = var.split(".", 1)
                if attr == "output":
                    key = f"__task_output_{task_id}"
                    output = process_properties.get(key)
                    return str(output) if output is not None else ""
            return str(process_properties.get(var, ""))

        return re.sub(r"\{\{(\w+(?:\.\w+)?)\}\}", replace_var, value)

    schema = copy.deepcopy(schema)
    # Resolve top-level description (used as form_description in the template)
    if "description" in schema and isinstance(schema["description"], str):
        schema["description"] = _resolve(schema["description"])
    for field_schema in schema.get("properties", {}).values():
        if "default" in field_schema and isinstance(field_schema["default"], str):
            field_schema["default"] = _resolve(field_schema["default"])
        if "description" in field_schema and isinstance(field_schema["description"], str):
            field_schema["description"] = _resolve(field_schema["description"])
    return schema


def _fallback_schema(task_name: str) -> dict:
    """Build a fallback schema for tasks without a JSON Schema definition.

    Used by both human_task_form and human_task_submit so the same schema
    is rendered and validated consistently.
    """
    return {
        "type": "object",
        "title": task_name,
        "required": ["response"],
        "properties": {
            "response": {
                "type": "string",
                "title": "Response",
                "format": "multiline",
            },
        },
    }


async def human_task_form(request, task_id):
    """Render the JSON Schema form for a human task."""
    from zebra.forms import get_routes_from_definition, schema_to_form

    await engine.ensure_initialized()
    store = engine.get_store()

    task = await store.load_task(task_id)
    if not task:
        # Task doesn't exist - it was either completed (and deleted by the engine)
        # or never existed. Show a friendly "already completed" page.
        context = {
            "error_title": "Task Already Completed",
            "error_message": (
                "This task has already been completed and is no longer available. "
                "The workflow has continued automatically."
            ),
        }
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="p-4 text-amber-300">This task has already been completed.</div>',
                status=404,
            )
        return render(request, "pages/task_not_found.html", context, status=404)

    # Load process and definition
    process = await store.load_process(task.process_id)
    if not process:
        return HttpResponse("Process not found", status=404)

    definition = await store.load_definition(process.definition_id)
    if not definition:
        return HttpResponse("Definition not found", status=404)

    task_def = definition.tasks.get(task.task_definition_id)
    if not task_def:
        return HttpResponse("Task definition not found", status=404)

    # Extract schema and build form
    schema = task_def.properties.get("schema", {})
    if not schema:
        schema = _fallback_schema(task_def.name)

    # Resolve {{template}} variables in schema defaults from process properties
    proc_props = process.properties or {}
    schema = _resolve_schema_defaults(schema, proc_props)

    form = schema_to_form(schema)

    # Get available routes for conditional routing
    routings = [
        {"from": r.source_task_id, "to": r.dest_task_id, "condition": r.condition, "name": r.name}
        for r in definition.routings
    ]
    routes = get_routes_from_definition(task.task_definition_id, routings)

    # Collect prior task outputs so the template can show them as context.
    # Only include __task_output_* values, labelled by their task definition name,
    # so the user can see what earlier tasks produced before filling in this form.
    prior_outputs = {}
    for key, value in proc_props.items():
        if key.startswith("__task_output_"):
            task_def_id = key[len("__task_output_") :]
            label = (
                definition.tasks[task_def_id].name
                if task_def_id in definition.tasks
                else task_def_id
            )
            # Extract the human-readable part: if the output is a dict with a
            # "response" key (common LLM action pattern), show just that string.
            if isinstance(value, dict) and "response" in value:
                display_value = value["response"]
            else:
                display_value = value
            prior_outputs[label] = display_value

    context = {
        "task": {
            "id": task.id,
            "task_definition_id": task.task_definition_id,
            "state": task.state.value,
            "process_id": task.process_id,
        },
        "task_def": {
            "name": task_def.name,
            "properties": task_def.properties,
        },
        "form": form,
        "field_errors": {},
        "routes": routes,
        "process_name": definition.name,
        "form_description": schema.get("description", ""),
        "prior_outputs": prior_outputs,
    }

    if request.headers.get("HX-Request"):
        return render(request, "partials/human_task_form.html", context)
    return render(request, "pages/human_task.html", context)


@require_http_methods(["POST"])
async def human_task_submit(request, task_id):
    """Handle form submission for a human task."""
    from zebra.core.models import TaskResult
    from zebra.forms import coerce_form_data, schema_to_form, validate_form_data

    await engine.ensure_initialized()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    task = await store.load_task(task_id)
    if not task:
        return HttpResponse("Task not found", status=404)

    process = await store.load_process(task.process_id)
    definition = await store.load_definition(process.definition_id)
    task_def = definition.tasks.get(task.task_definition_id)

    schema = task_def.properties.get("schema", {})
    if not schema:
        schema = _fallback_schema(task_def.name)

    # Coerce and validate form data
    raw_data = dict(request.POST)
    # Django QueryDict gives lists for all values; flatten single values
    flat_data = {}
    for key, value in raw_data.items():
        if key in ("csrfmiddlewaretoken", "next_route"):
            continue
        if isinstance(value, list) and len(value) == 1:
            flat_data[key] = value[0]
        else:
            flat_data[key] = value

    coerced = coerce_form_data(schema, flat_data)
    errors = validate_form_data(schema, coerced)

    if errors:
        # Re-render form with errors and previously submitted values
        from zebra.forms import get_routes_from_definition

        form = schema_to_form(schema)
        routings = [
            {
                "from": r.source_task_id,
                "to": r.dest_task_id,
                "condition": r.condition,
                "name": r.name,
            }
            for r in definition.routings
        ]
        routes = get_routes_from_definition(task.task_definition_id, routings)

        field_errors: dict[str, list[str]] = {}
        for e in errors:
            field_errors.setdefault(e.field, []).append(e.message)

        context = {
            "task": {
                "id": task.id,
                "task_definition_id": task.task_definition_id,
                "state": task.state.value,
                "process_id": task.process_id,
            },
            "task_def": {"name": task_def.name, "properties": task_def.properties},
            "form": form,
            "field_errors": field_errors,
            "submitted_values": coerced,
            "routes": routes,
            "process_name": definition.name,
            "form_description": schema.get("description", ""),
        }
        return render(request, "partials/human_task_form.html", context)

    # Complete the task
    next_route = request.POST.get("next_route")
    result = TaskResult(success=True, output=coerced, next_route=next_route)

    try:
        new_tasks = await wf_engine.complete_task(task_id, result)
    except Exception as e:
        logger.exception("Failed to complete task %s", task_id)
        return HttpResponse(f"Error completing task: {e}", status=500)

    # Return success partial
    new_tasks_data = [
        {
            "id": t.id,
            "task_definition_id": t.task_definition_id,
            "state": t.state.value,
        }
        for t in new_tasks
    ]

    context = {
        "task_id": task_id,
        "task_name": task_def.name,
        "new_tasks": new_tasks_data,
    }
    return render(request, "partials/human_task_complete.html", context)

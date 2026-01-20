"""Web views for Zebra UI using Django templates + HTMX."""

import logging
from asgiref.sync import async_to_sync

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml

from zebra_web.api import engine

logger = logging.getLogger(__name__)


def ensure_engine():
    """Ensure the Zebra engine is initialized."""
    async_to_sync(engine.ensure_initialized)()


def pydantic_to_dict(obj):
    """Convert a Pydantic model to a dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    elif hasattr(obj, "dict"):
        return obj.dict()
    return obj


# =============================================================================
# Dashboard
# =============================================================================


def dashboard(request):
    """Dashboard view with stats overview."""
    ensure_engine()
    store = engine.get_store()

    definitions = async_to_sync(store.list_definitions)()
    processes = async_to_sync(store.list_processes)(include_completed=True)

    running = [p for p in processes if p.state == ProcessState.RUNNING]
    completed = [p for p in processes if p.state == ProcessState.COMPLETE]
    failed = [p for p in processes if p.state == ProcessState.FAILED]

    # Get pending tasks
    pending_tasks = []
    for process in running:
        tasks = async_to_sync(store.load_tasks_for_process)(process.id)
        definition = async_to_sync(store.load_definition)(process.definition_id)
        for task in tasks:
            if task.state.value == "READY" and definition:
                task_def = definition.tasks.get(task.task_definition_id)
                if task_def and not task_def.auto:
                    pending_tasks.append(
                        {
                            **pydantic_to_dict(task),
                            "process_definition_name": definition.name,
                            "task_definition_name": task_def.name,
                        }
                    )

    context = {
        "definitions_count": len(definitions),
        "running_count": len(running),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "pending_tasks_count": len(pending_tasks),
        "recent_processes": [pydantic_to_dict(p) for p in processes[:5]],
        "pending_tasks": pending_tasks[:5],
        "health": "healthy",
    }

    # Add definition names to processes
    def_map = {d.id: d.name for d in definitions}
    for p in context["recent_processes"]:
        p["definition_name"] = def_map.get(p["definition_id"], "Unknown")

    return render(request, "pages/dashboard.html", context)


# =============================================================================
# Definitions
# =============================================================================


def definitions_list(request):
    """List all workflow definitions."""
    ensure_engine()
    store = engine.get_store()

    definitions = async_to_sync(store.list_definitions)()
    definitions_data = []
    for d in definitions:
        data = pydantic_to_dict(d)
        data["task_count"] = len(d.tasks)
        definitions_data.append(data)

    context = {"definitions": definitions_data}

    if request.headers.get("HX-Request"):
        return render(request, "partials/definitions_list.html", context)
    return render(request, "pages/definitions.html", context)


def definition_detail(request, definition_id):
    """View a specific definition."""
    ensure_engine()
    store = engine.get_store()

    definition = async_to_sync(store.load_definition)(definition_id)
    if not definition:
        return HttpResponse("Definition not found", status=404)

    context = {"definition": pydantic_to_dict(definition)}
    return render(request, "pages/definition_detail.html", context)


@require_http_methods(["POST"])
def definition_create(request):
    """Create a new definition from YAML."""
    ensure_engine()
    store = engine.get_store()

    yaml_content = request.POST.get("yaml_content", "")
    if not yaml_content.strip():
        return HttpResponse("YAML content required", status=400)

    try:
        definition = load_definition_from_yaml(yaml_content)
        async_to_sync(store.save_definition)(definition)

        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = f"/definitions/{definition.id}/"
            return response
        return redirect("definition_detail", definition_id=definition.id)
    except Exception as e:
        logger.exception("Failed to create definition")
        return HttpResponse(f"Error: {e}", status=400)


@require_http_methods(["DELETE"])
def definition_delete(request, definition_id):
    """Delete a definition."""
    ensure_engine()
    store = engine.get_store()

    async_to_sync(store.delete_definition)(definition_id)

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = "/definitions/"
        return response
    return redirect("definitions_list")


# =============================================================================
# Processes
# =============================================================================


def processes_list(request):
    """List all processes."""
    ensure_engine()
    store = engine.get_store()

    include_completed = request.GET.get("include_completed") == "true"
    state_filter = request.GET.get("state")

    processes = async_to_sync(store.list_processes)(include_completed=include_completed)

    if state_filter:
        processes = [p for p in processes if p.state.value.lower() == state_filter.lower()]

    # Get definition names
    definitions = async_to_sync(store.list_definitions)()
    def_map = {d.id: d.name for d in definitions}

    processes_data = []
    for p in processes:
        data = pydantic_to_dict(p)
        data["definition_name"] = def_map.get(p.definition_id, "Unknown")
        processes_data.append(data)

    context = {
        "processes": processes_data,
        "definitions": [pydantic_to_dict(d) for d in definitions],
        "include_completed": include_completed,
        "state_filter": state_filter,
    }

    if request.headers.get("HX-Request"):
        return render(request, "partials/processes_list.html", context)
    return render(request, "pages/processes.html", context)


def process_detail(request, process_id):
    """View a specific process."""
    ensure_engine()
    store = engine.get_store()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return HttpResponse("Process not found", status=404)

    tasks = async_to_sync(store.load_tasks_for_process)(process_id)
    foes = async_to_sync(store.load_foes_for_process)(process_id)
    definition = async_to_sync(store.load_definition)(process.definition_id)

    context = {
        "process": pydantic_to_dict(process),
        "tasks": [pydantic_to_dict(t) for t in tasks],
        "foes": [pydantic_to_dict(f) for f in foes],
        "definition": pydantic_to_dict(definition) if definition else None,
    }
    return render(request, "pages/process_detail.html", context)


@require_http_methods(["POST"])
def process_start(request):
    """Start a new process."""
    ensure_engine()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    definition_id = request.POST.get("definition_id")
    if not definition_id:
        return HttpResponse("Definition ID required", status=400)

    definition = async_to_sync(store.load_definition)(definition_id)
    if not definition:
        return HttpResponse("Definition not found", status=404)

    try:
        # Parse properties JSON if provided
        import json

        properties_str = request.POST.get("properties", "{}")
        properties = json.loads(properties_str) if properties_str else {}

        process = async_to_sync(wf_engine.create_process)(
            definition=definition, properties=properties
        )
        process = async_to_sync(wf_engine.start_process)(process.id)

        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = f"/processes/{process.id}/"
            return response
        return redirect("process_detail", process_id=process.id)
    except Exception as e:
        logger.exception("Failed to start process")
        return HttpResponse(f"Error: {e}", status=400)


@require_http_methods(["POST"])
def process_pause(request, process_id):
    """Pause a running process."""
    ensure_engine()
    store = engine.get_store()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return HttpResponse("Process not found", status=404)

    if process.state != ProcessState.RUNNING:
        return HttpResponse(f"Cannot pause process in state {process.state.value}", status=400)

    process = process.model_copy(update={"state": ProcessState.PAUSED})
    async_to_sync(store.save_process)(process)

    if request.headers.get("HX-Request"):
        return render(
            request, "partials/process_status.html", {"process": pydantic_to_dict(process)}
        )
    return redirect("process_detail", process_id=process_id)


@require_http_methods(["POST"])
def process_resume(request, process_id):
    """Resume a paused process."""
    ensure_engine()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return HttpResponse("Process not found", status=404)

    if process.state != ProcessState.PAUSED:
        return HttpResponse(f"Cannot resume process in state {process.state.value}", status=400)

    process = async_to_sync(wf_engine.resume_process)(process_id)

    if request.headers.get("HX-Request"):
        return render(
            request, "partials/process_status.html", {"process": pydantic_to_dict(process)}
        )
    return redirect("process_detail", process_id=process_id)


@require_http_methods(["DELETE"])
def process_delete(request, process_id):
    """Delete a process."""
    ensure_engine()
    store = engine.get_store()

    async_to_sync(store.delete_process)(process_id)

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = "/processes/"
        return response
    return redirect("processes_list")


# =============================================================================
# Tasks
# =============================================================================


def tasks_list(request):
    """List pending tasks."""
    ensure_engine()
    store = engine.get_store()

    processes = async_to_sync(store.list_processes)(include_completed=False)

    pending_tasks = []
    for process in processes:
        if process.state == ProcessState.RUNNING:
            tasks = async_to_sync(store.load_tasks_for_process)(process.id)
            definition = async_to_sync(store.load_definition)(process.definition_id)
            for task in tasks:
                if task.state.value == "READY" and definition:
                    task_def = definition.tasks.get(task.task_definition_id)
                    if task_def and not task_def.auto:
                        pending_tasks.append(
                            {
                                **pydantic_to_dict(task),
                                "process_definition_name": definition.name,
                                "task_definition_name": task_def.name,
                            }
                        )

    context = {"tasks": pending_tasks}

    if request.headers.get("HX-Request"):
        return render(request, "partials/tasks_list.html", context)
    return render(request, "pages/tasks.html", context)


def task_detail(request, task_id):
    """View a specific task."""
    ensure_engine()
    store = engine.get_store()

    task = async_to_sync(store.load_task)(task_id)
    if not task:
        return HttpResponse("Task not found", status=404)

    process = async_to_sync(store.load_process)(task.process_id)
    definition = async_to_sync(store.load_definition)(process.definition_id) if process else None
    task_def = definition.tasks.get(task.task_definition_id) if definition else None

    context = {
        "task": pydantic_to_dict(task),
        "process": pydantic_to_dict(process) if process else None,
        "definition": pydantic_to_dict(definition) if definition else None,
        "task_definition": pydantic_to_dict(task_def) if task_def else None,
    }
    return render(request, "pages/task_detail.html", context)


@require_http_methods(["POST"])
def task_complete(request, task_id):
    """Complete a pending task."""
    ensure_engine()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    task = async_to_sync(store.load_task)(task_id)
    if not task:
        return HttpResponse("Task not found", status=404)

    try:
        import json

        result_str = request.POST.get("result", "{}")
        result_data = json.loads(result_str) if result_str else {}
        next_route = request.POST.get("next_route") or None

        result = TaskResult(success=True, output=result_data, next_route=next_route)
        async_to_sync(wf_engine.complete_task)(task_id, result)

        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = "/tasks/"
            return response
        return redirect("tasks_list")
    except Exception as e:
        logger.exception("Failed to complete task")
        return HttpResponse(f"Error: {e}", status=400)

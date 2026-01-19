"""API views for Zebra workflow management."""

import logging
from asgiref.sync import async_to_sync

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml

from zebra_web.api import engine
from zebra_web.api.serializers import (
    ProcessDefinitionSerializer,
    ProcessDefinitionListSerializer,
    ProcessInstanceSerializer,
    ProcessInstanceDetailSerializer,
    ProcessInstanceListSerializer,
    TaskInstanceSerializer,
    CreateDefinitionRequestSerializer,
    StartProcessRequestSerializer,
    CompleteTaskRequestSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Helper functions
# =============================================================================


def ensure_engine():
    """Ensure the Zebra engine is initialized."""
    async_to_sync(engine.ensure_initialized)()


def pydantic_to_dict(obj):
    """Convert a Pydantic model to a dict for serialization."""
    if hasattr(obj, "model_dump"):
        # Use mode='json' to serialize enums to their values
        return obj.model_dump(mode="json")
    elif hasattr(obj, "dict"):
        return obj.dict()
    return obj


# =============================================================================
# Definition endpoints
# =============================================================================


@api_view(["GET", "POST"])
def definitions_list(request):
    """List all definitions or create a new one."""
    ensure_engine()
    store = engine.get_store()

    if request.method == "GET":
        definitions = async_to_sync(store.list_definitions)()
        serializer = ProcessDefinitionListSerializer(
            [pydantic_to_dict(d) for d in definitions], many=True
        )
        return Response(serializer.data)

    elif request.method == "POST":
        req_serializer = CreateDefinitionRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            yaml_content = req_serializer.validated_data["yaml_content"]
            definition = load_definition_from_yaml(yaml_content)
            async_to_sync(store.save_definition)(definition)

            serializer = ProcessDefinitionSerializer(pydantic_to_dict(definition))
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("Failed to create definition")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "DELETE"])
def definition_detail(request, definition_id):
    """Get or delete a specific definition."""
    ensure_engine()
    store = engine.get_store()

    definition = async_to_sync(store.load_definition)(definition_id)
    if not definition:
        return Response(
            {"error": f"Definition '{definition_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = ProcessDefinitionSerializer(pydantic_to_dict(definition))
        return Response(serializer.data)

    elif request.method == "DELETE":
        async_to_sync(store.delete_definition)(definition_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Process endpoints
# =============================================================================


@api_view(["GET", "POST"])
def processes_list(request):
    """List all processes or start a new one."""
    ensure_engine()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    if request.method == "GET":
        # Get filter parameters
        definition_id = request.query_params.get("definition_id")
        include_completed = request.query_params.get("include_completed", "false").lower() == "true"
        state = request.query_params.get("state")

        processes = async_to_sync(store.list_processes)(
            definition_id=definition_id, include_completed=include_completed
        )

        # Filter by state if specified
        if state:
            processes = [p for p in processes if p.state.value == state]

        # Add definition name to each process
        result = []
        for p in processes:
            data = pydantic_to_dict(p)
            definition = async_to_sync(store.load_definition)(p.definition_id)
            data["definition_name"] = definition.name if definition else None
            result.append(data)

        serializer = ProcessInstanceListSerializer(result, many=True)
        return Response(serializer.data)

    elif request.method == "POST":
        req_serializer = StartProcessRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            definition_id = req_serializer.validated_data["definition_id"]
            properties = req_serializer.validated_data.get("properties", {})

            # Load the definition
            definition = async_to_sync(store.load_definition)(definition_id)
            if not definition:
                return Response(
                    {"error": f"Definition '{definition_id}' not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Create the process
            process = async_to_sync(wf_engine.create_process)(
                definition=definition, properties=properties
            )

            # Start the process
            process = async_to_sync(wf_engine.start_process)(process.id)

            serializer = ProcessInstanceSerializer(pydantic_to_dict(process))
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("Failed to start process")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "DELETE"])
def process_detail(request, process_id):
    """Get or delete a specific process."""
    ensure_engine()
    store = engine.get_store()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        # Get full details including tasks and FOEs
        data = pydantic_to_dict(process)

        # Load tasks
        tasks = async_to_sync(store.load_tasks_for_process)(process_id)
        data["tasks"] = [pydantic_to_dict(t) for t in tasks]

        # Load FOEs
        foes = async_to_sync(store.load_foes_for_process)(process_id)
        data["foes"] = [pydantic_to_dict(f) for f in foes]

        # Load definition
        definition = async_to_sync(store.load_definition)(process.definition_id)
        if definition:
            data["definition"] = pydantic_to_dict(definition)

        serializer = ProcessInstanceDetailSerializer(data)
        return Response(serializer.data)

    elif request.method == "DELETE":
        async_to_sync(store.delete_process)(process_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def process_pause(request, process_id):
    """Pause a running process."""
    ensure_engine()
    store = engine.get_store()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if process.state != ProcessState.RUNNING:
        return Response(
            {"error": f"Cannot pause process in state '{process.state.value}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    process.state = ProcessState.PAUSED
    async_to_sync(store.save_process)(process)

    serializer = ProcessInstanceSerializer(pydantic_to_dict(process))
    return Response(serializer.data)


@api_view(["POST"])
def process_resume(request, process_id):
    """Resume a paused process."""
    ensure_engine()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if process.state != ProcessState.PAUSED:
        return Response(
            {"error": f"Cannot resume process in state '{process.state.value}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Resume the process
    process = async_to_sync(wf_engine.resume_process)(process_id)

    serializer = ProcessInstanceSerializer(pydantic_to_dict(process))
    return Response(serializer.data)


# =============================================================================
# Task endpoints
# =============================================================================


@api_view(["GET"])
def process_tasks(request, process_id):
    """List all tasks for a process."""
    ensure_engine()
    store = engine.get_store()

    process = async_to_sync(store.load_process)(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    tasks = async_to_sync(store.load_tasks_for_process)(process_id)
    serializer = TaskInstanceSerializer([pydantic_to_dict(t) for t in tasks], many=True)
    return Response(serializer.data)


@api_view(["GET"])
def task_detail(request, task_id):
    """Get a specific task."""
    ensure_engine()
    store = engine.get_store()

    task = async_to_sync(store.load_task)(task_id)
    if not task:
        return Response({"error": f"Task '{task_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TaskInstanceSerializer(pydantic_to_dict(task))
    return Response(serializer.data)


@api_view(["POST"])
def task_complete(request, task_id):
    """Complete a pending task."""
    ensure_engine()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    task = async_to_sync(store.load_task)(task_id)
    if not task:
        return Response({"error": f"Task '{task_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

    req_serializer = CompleteTaskRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result_data = req_serializer.validated_data.get("result", {})
        next_route = req_serializer.validated_data.get("next_route")

        # Create TaskResult
        result = TaskResult(success=True, output=result_data, next_route=next_route)

        # Complete the task
        async_to_sync(wf_engine.complete_task)(task_id, result)

        # Reload the task to get updated state
        task = async_to_sync(store.load_task)(task_id)
        serializer = TaskInstanceSerializer(pydantic_to_dict(task))
        return Response(serializer.data)
    except Exception as e:
        logger.exception("Failed to complete task")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def pending_tasks(request):
    """Get all pending tasks across all processes."""
    ensure_engine()
    store = engine.get_store()

    # Get all running processes
    processes = async_to_sync(store.list_processes)(include_completed=False)

    pending = []
    for process in processes:
        if process.state == ProcessState.RUNNING:
            tasks = async_to_sync(store.load_tasks_for_process)(process.id)
            for task in tasks:
                # Check if task is waiting for input (not auto)
                if task.state.value == "READY":
                    definition = async_to_sync(store.load_definition)(process.definition_id)
                    if definition:
                        task_def = definition.tasks.get(task.task_definition_id)
                        if task_def and not task_def.auto:
                            data = pydantic_to_dict(task)
                            data["process_definition_name"] = definition.name
                            data["task_definition_name"] = task_def.name
                            pending.append(data)

    serializer = TaskInstanceSerializer(pending, many=True)
    return Response(serializer.data)


# =============================================================================
# Health check
# =============================================================================


@api_view(["GET"])
def health_check(request):
    """Health check endpoint."""
    try:
        ensure_engine()
        return Response({"status": "healthy", "engine": "initialized"})
    except Exception as e:
        return Response(
            {"status": "unhealthy", "error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

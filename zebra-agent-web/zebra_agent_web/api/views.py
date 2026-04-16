"""REST API views for Zebra Agent.

Provides async JSON API endpoints for:
- Agent operations (workflows, goals, runs)
- Execution monitoring (processes, tasks)
"""

import asyncio
import logging
import threading
import uuid

from asgiref.sync import async_to_sync, sync_to_async
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from zebra.core.models import TaskResult

from zebra_agent_web.api import agent_engine, engine
from zebra_agent_web.api.serializers import (
    CompleteTaskRequestSerializer,
    CreateWorkflowRequestSerializer,
    ExecuteGoalRequestSerializer,
    GoalAcceptedSerializer,
    ProcessInstanceDetailSerializer,
    ProcessInstanceListSerializer,
    RateRunRequestSerializer,
    TaskInstanceSerializer,
    WorkflowDetailSerializer,
    WorkflowInfoSerializer,
    WorkflowRunSerializer,
    WorkflowStatsSerializer,
)

logger = logging.getLogger(__name__)

# run_ids for goals started via POST /api/goals/ that are still in flight
_active_api_runs: set[str] = set()


def is_api_run_active(run_id: str) -> bool:
    """Return True if a background API goal thread is still running."""
    return run_id in _active_api_runs


# =============================================================================
# Helper functions
# =============================================================================


def pydantic_to_dict(obj):
    """Convert a Pydantic model to a dict for serialization."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    elif hasattr(obj, "dict"):
        return obj.dict()
    return obj


# =============================================================================
# Health check
# =============================================================================


@api_view(["GET"])
async def health_check(request):
    """Health check endpoint."""
    try:
        await agent_engine.ensure_initialized()
        return Response({"status": "healthy", "agent": "initialized"})
    except Exception as e:
        return Response(
            {"status": "unhealthy", "error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


# =============================================================================
# Workflow endpoints
# =============================================================================


@api_view(["GET", "POST"])
async def workflows_list(request):
    """List all workflows or create a new one."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()

    if request.method == "GET":
        workflows = await library.list_workflows()
        serializer = WorkflowInfoSerializer(
            [
                {
                    "name": w.name,
                    "description": w.description,
                    "tags": w.tags,
                    "version": w.version,
                    "use_when": w.use_when,
                    "success_rate": w.success_rate,
                    "use_count": w.use_count,
                }
                for w in workflows
            ],
            many=True,
        )
        return Response(serializer.data)

    elif request.method == "POST":
        req_serializer = CreateWorkflowRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            yaml_content = req_serializer.validated_data["yaml_content"]
            workflow_name = library.add_workflow(yaml_content)

            # Return the created workflow info
            workflows = await library.list_workflows()
            workflow = next((w for w in workflows if w.name == workflow_name), None)
            if workflow:
                serializer = WorkflowInfoSerializer(
                    {
                        "name": workflow.name,
                        "description": workflow.description,
                        "tags": workflow.tags,
                        "version": workflow.version,
                        "use_when": workflow.use_when,
                        "success_rate": workflow.success_rate,
                        "use_count": workflow.use_count,
                    }
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response({"name": workflow_name}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("Failed to create workflow")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "DELETE"])
async def workflow_detail(request, workflow_name):
    """Get or delete a specific workflow."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()
    metrics = agent_engine.get_metrics()

    try:
        yaml_content = library.get_workflow_yaml(workflow_name)
    except ValueError:
        return Response(
            {"error": f"Workflow '{workflow_name}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        stats = await metrics.get_stats(workflow_name)
        workflows = await library.list_workflows()
        workflow_info = next((w for w in workflows if w.name == workflow_name), None)

        data = {
            "name": workflow_name,
            "description": workflow_info.description if workflow_info else "",
            "tags": workflow_info.tags if workflow_info else [],
            "version": workflow_info.version if workflow_info else 1,
            "use_when": workflow_info.use_when if workflow_info else None,
            "success_rate": workflow_info.success_rate if workflow_info else 0.0,
            "use_count": workflow_info.use_count if workflow_info else 0,
            "yaml_content": yaml_content,
            "stats": {
                "total_runs": stats.total_runs,
                "successful_runs": stats.successful_runs,
                "success_rate": stats.success_rate,
                "avg_rating": stats.avg_rating,
                "last_used": stats.last_used.isoformat() if stats.last_used else None,
            },
        }
        serializer = WorkflowDetailSerializer(data)
        return Response(serializer.data)

    elif request.method == "DELETE":
        try:
            import yaml

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
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.exception("Failed to delete workflow")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
async def workflow_stats(request, workflow_name):
    """Get statistics for a specific workflow."""
    await agent_engine.ensure_initialized()
    library = agent_engine.get_library()
    metrics = agent_engine.get_metrics()

    try:
        library.get_workflow_yaml(workflow_name)  # Verify exists
    except ValueError:
        return Response(
            {"error": f"Workflow '{workflow_name}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    stats = await metrics.get_stats(workflow_name)
    serializer = WorkflowStatsSerializer(
        {
            "total_runs": stats.total_runs,
            "successful_runs": stats.successful_runs,
            "success_rate": stats.success_rate,
            "avg_rating": stats.avg_rating,
            "last_used": stats.last_used,
        }
    )
    return Response(serializer.data)


# =============================================================================
# Goal execution endpoints
# =============================================================================


# run_ids for dream cycles started via POST /api/dream-cycle/ that are still in flight
_active_dream_runs: set[str] = set()


def _run_dream_cycle_in_background(run_id: str) -> None:
    """Fire run_dream_cycle in a daemon thread with its own event loop.

    Returns immediately; the caller polls GET /api/runs/<run_id>/status/.
    """

    _active_dream_runs.add(run_id)

    async def _run():
        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()
        await agent_loop.run_dream_cycle()

    def _thread():
        try:
            asyncio.run(_run())
        except Exception:
            logger.exception("Background dream cycle failed for run %s", run_id)
        finally:
            _active_dream_runs.discard(run_id)

    t = threading.Thread(target=_thread, daemon=True, name=f"dream-{run_id[:8]}")
    t.start()


def _run_goal_in_background(run_id: str, goal: str, model: str | None = None) -> None:
    """Fire process_goal in a daemon thread with its own event loop.

    Returns immediately; the caller polls GET /api/runs/<run_id>/status/.
    Uses asyncio.run() in a fresh thread to avoid deadlocking the ASGI
    event loop that is already running inside Daphne.
    """

    _active_api_runs.add(run_id)

    async def _run():
        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()
        await agent_loop.process_goal(goal, run_id=run_id, model=model)

    def _thread():
        try:
            asyncio.run(_run())
        except Exception:
            logger.exception("Background goal execution failed for run %s", run_id)
        finally:
            _active_api_runs.discard(run_id)

    t = threading.Thread(target=_thread, daemon=True, name=f"goal-{run_id[:8]}")
    t.start()


@api_view(["POST"])
def execute_goal(request):
    """Start goal execution and return immediately with a run_id.

    The agent runs in a background thread.  Poll
    GET /api/runs/<run_id>/status/ to check for completion.

    Returns 202 Accepted with::

        {
            "run_id": "<uuid>",
            "status": "processing",
            "message": "Goal execution started",
            "status_url": "/api/runs/<run_id>/status/"
        }
    """
    req_serializer = ExecuteGoalRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    goal = req_serializer.validated_data["goal"]
    model_name = req_serializer.validated_data.get("model")
    run_id = str(uuid.uuid4())

    # Resolve friendly model name (e.g. "haiku") to API model ID
    from zebra_tasks.llm.models import resolve_model_name

    resolved_model = resolve_model_name(model_name) if model_name else None

    try:
        _run_goal_in_background(run_id, goal, model=resolved_model)
    except Exception as e:
        logger.exception("Failed to start goal execution")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = GoalAcceptedSerializer(
        {
            "run_id": run_id,
            "status": "processing",
            "message": "Goal execution started",
            "status_url": f"/api/runs/{run_id}/status/",
        }
    )
    return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
def dream_cycle(request):
    """Start the Dream Cycle self-improvement workflow.

    The dream cycle runs in a background thread. Poll
    GET /api/runs/<run_id>/status/ to check for completion.

    Returns 202 Accepted with::

        {
            "run_id": "<uuid>",
            "status": "processing",
            "message": "Dream cycle started"
        }
    """
    run_id = str(uuid.uuid4())

    try:
        _run_dream_cycle_in_background(run_id)
    except Exception as e:
        logger.exception("Failed to start dream cycle")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            "run_id": run_id,
            "status": "processing",
            "message": "Dream cycle started",
        },
        status=status.HTTP_202_ACCEPTED,
    )


# =============================================================================
# Run endpoints
# =============================================================================


@api_view(["GET"])
async def runs_list(request):
    """List recent runs."""
    await agent_engine.ensure_initialized()
    metrics = agent_engine.get_metrics()

    limit = int(request.query_params.get("limit", 50))
    workflow_name = request.query_params.get("workflow")

    if workflow_name:
        runs = await metrics.get_runs_for_workflow(workflow_name, limit=limit)
    else:
        runs = await metrics.get_recent_runs(limit=limit)

    serializer = WorkflowRunSerializer(
        [
            {
                "id": r.id,
                "workflow_name": r.workflow_name,
                "goal": r.goal,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "success": r.success,
                "user_rating": r.user_rating,
                "tokens_used": r.tokens_used,
                "error": r.error,
                "output": r.output,
            }
            for r in runs
        ],
        many=True,
    )
    return Response(serializer.data)


@api_view(["GET"])
async def run_detail(request, run_id):
    """Get details of a specific run."""
    await agent_engine.ensure_initialized()
    metrics = agent_engine.get_metrics()

    run = await metrics.get_run(run_id)
    if not run:
        return Response({"error": f"Run '{run_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = WorkflowRunSerializer(
        {
            "id": run.id,
            "workflow_name": run.workflow_name,
            "goal": run.goal,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "success": run.success,
            "user_rating": run.user_rating,
            "tokens_used": run.tokens_used,
            "error": run.error,
            "output": run.output,
        }
    )
    return Response(serializer.data)


@api_view(["POST"])
def run_rate(request, run_id):
    """Rate a run."""
    req_serializer = RateRunRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    rating = req_serializer.validated_data["rating"]

    async def _rate():
        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()
        metrics = agent_engine.get_metrics()

        run = await metrics.get_run(run_id)
        if run is None:
            return None
        await agent_loop.record_rating(run_id, rating)
        return True

    try:
        result = async_to_sync(_rate)()
    except Exception as e:
        logger.exception("Failed to rate run")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    if result is None:
        return Response({"error": f"Run '{run_id}' not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"run_id": run_id, "rating": rating})


def _run_status_impl(run_id):
    """Sync implementation for run_status using async_to_sync."""

    async def _get_data():
        await agent_engine.ensure_initialized()
        metrics = agent_engine.get_metrics()
        return await metrics.get_run(run_id)

    return async_to_sync(_get_data)()


@api_view(["GET"])
def run_status(request, run_id):
    """Get current status of a run (for recovery if WebSocket disconnects).

    Returns:
    - status: "processing" | "completed" | "failed" | "not_found"
    - Additional fields depending on status
    """
    # Import here to avoid circular import
    from zebra_agent_web.api.web_views import is_task_active

    run = _run_status_impl(run_id)

    if run is None:
        # Check if it's still being processed (web UI task or API background thread)
        if is_task_active(run_id) or is_api_run_active(run_id):
            return Response(
                {
                    "status": "processing",
                    "run_id": run_id,
                    "message": "Goal execution in progress",
                }
            )
        return Response(
            {"status": "not_found", "error": f"Run '{run_id}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Run exists - check if completed
    if run.completed_at is None:
        return Response(
            {
                "status": "processing",
                "run_id": run.id,
                "workflow_name": run.workflow_name,
                "message": "Workflow execution in progress",
            }
        )

    # Completed (success or failure)
    from zebra_tasks.llm.models import friendly_model_name

    return Response(
        {
            "status": "completed" if run.success else "failed",
            "run_id": run.id,
            "workflow_name": run.workflow_name,
            "success": run.success,
            "output": str(run.output) if run.output else None,
            "error": run.error,
            "tokens_used": run.tokens_used,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "model": friendly_model_name(run.model),
        }
    )


def _run_diagram_impl(run_id):
    """Implementation for run_diagram that handles async operations.

    Falls back to running engine processes when no metrics record exists yet
    (which is common during execution, since metrics are recorded at completion).
    """
    from asgiref.sync import async_to_sync

    from zebra_agent_web.diagram import generate_workflow_svg

    # Initialize and get data using async_to_sync
    async def _get_data():
        await agent_engine.ensure_initialized()
        await engine.ensure_initialized()
        metrics = agent_engine.get_metrics()
        library = agent_engine.get_library()
        store = engine.get_store()

        run = await metrics.get_run(run_id)
        task_executions = []
        workflow_name = None
        completed = False

        if run is not None:
            workflow_name = run.workflow_name
            task_executions = await metrics.get_task_executions(run_id)
            completed = run.completed_at is not None
        else:
            # No metrics record yet - look up workflow_name from running processes.
            # This happens during execution before RecordMetricsAction fires.
            running_processes = await store.get_running_processes()
            for process in running_processes:
                props = process.properties or {}
                if props.get("run_id") == run_id:
                    workflow_name = props.get("workflow_name")
                    break
            if workflow_name is None:
                return None, None, None, None, "not_found"

        if not workflow_name:
            return None, None, None, None, "no_workflow"

        try:
            workflow_definition = library.get_workflow(workflow_name)
        except ValueError:
            return None, None, None, None, "workflow_not_found"

        return workflow_name, workflow_definition, task_executions, completed, None

    workflow_name, workflow_definition, task_executions, completed, error = async_to_sync(
        _get_data
    )()

    if error:
        return None, error

    workflow_svg = generate_workflow_svg(workflow_definition, task_executions)
    return {
        "run_id": run_id,
        "workflow_name": workflow_name,
        "svg": workflow_svg,
        "task_count": len(task_executions),
        "completed": completed,
    }, None


@api_view(["GET"])
def run_diagram(request, run_id):
    """Get the workflow diagram SVG for a run.

    Returns the workflow visualization with current task execution states.
    This endpoint is used for live updates during goal processing.
    """
    result, error = _run_diagram_impl(run_id)

    if error == "not_found":
        return Response(
            {"error": f"Run '{run_id}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    if error == "no_workflow":
        return Response(
            {"error": "Workflow not yet selected"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if error == "workflow_not_found":
        return Response(
            {"error": "Workflow not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(result)


# =============================================================================
# Execution monitoring endpoints (read-only + task completion)
# =============================================================================


@api_view(["GET"])
async def budget_status(request):
    """Return current budget status and goal queue depth.

    Response::

        {
            "daily_budget": 50.0,
            "spent_today": 1.234,
            "remaining": 48.766,
            "paced_allowance": 12.5,
            "available": 11.266,
            "pct_used": "2.5%",
            "reset_hour": 0,
            "hours_since_reset": 6.0,
            "queue_depth": 3
        }
    """
    await agent_engine.ensure_initialized()

    budget_manager = agent_engine.get_budget_manager()
    status = await budget_manager.get_status()

    # Add queue depth
    from zebra.core.models import ProcessState
    from zebra_agent_web.api.engine import get_engine

    wf_engine = get_engine()
    created_processes = await wf_engine.store.get_processes_by_state(
        ProcessState.CREATED, exclude_children=True
    )
    status["queue_depth"] = len(created_processes)

    return Response(status)


@api_view(["GET"])
async def processes_list(request):
    """List process instances (for monitoring agent workflow execution)."""
    await engine.ensure_initialized()
    store = engine.get_store()

    include_completed = request.query_params.get("include_completed", "false").lower() == "true"
    state = request.query_params.get("state")

    processes = await store.list_processes(include_completed=include_completed)

    # Filter by state if specified
    if state:
        processes = [p for p in processes if p.state.value == state]

    # Add definition name to each process
    result = []
    for p in processes:
        data = pydantic_to_dict(p)
        definition = await store.load_definition(p.definition_id)
        data["definition_name"] = definition.name if definition else None
        result.append(data)

    serializer = ProcessInstanceListSerializer(result, many=True)
    return Response(serializer.data)


@api_view(["GET"])
async def process_detail(request, process_id):
    """Get details of a specific process."""
    await engine.ensure_initialized()
    store = engine.get_store()

    process = await store.load_process(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    data = pydantic_to_dict(process)

    # Load tasks
    tasks = await store.load_tasks_for_process(process_id)
    data["tasks"] = [pydantic_to_dict(t) for t in tasks]

    # Load FOEs
    foes = await store.load_foes_for_process(process_id)
    data["foes"] = [pydantic_to_dict(f) for f in foes]

    # Load definition
    definition = await store.load_definition(process.definition_id)
    if definition:
        data["definition"] = pydantic_to_dict(definition)

    serializer = ProcessInstanceDetailSerializer(data)
    return Response(serializer.data)


@api_view(["GET"])
async def process_tasks(request, process_id):
    """Get tasks for a specific process."""
    await engine.ensure_initialized()
    store = engine.get_store()

    process = await store.load_process(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    tasks = await store.load_tasks_for_process(process_id)
    serializer = TaskInstanceSerializer([pydantic_to_dict(t) for t in tasks], many=True)
    return Response(serializer.data)


@api_view(["GET"])
async def process_pending_tasks(request, process_id):
    """Get pending human tasks for a process, enriched with definition and form schema.

    Returns tasks in READY state with auto=False, including their task definition
    properties and JSON Schema form definition for rendering UI forms.
    """
    await engine.ensure_initialized()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    process = await store.load_process(process_id)
    if not process:
        return Response(
            {"error": f"Process '{process_id}' not found"}, status=status.HTTP_404_NOT_FOUND
        )

    definition = await store.load_definition(process.definition_id)
    if not definition:
        return Response(
            {"error": f"Definition '{process.definition_id}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    pending = await wf_engine.get_pending_tasks(process_id)

    result = []
    for task in pending:
        task_def = definition.tasks.get(task.task_definition_id)
        if not task_def or task_def.auto:
            continue

        task_data = pydantic_to_dict(task)
        task_data["definition"] = {
            "id": task_def.id,
            "name": task_def.name,
            "auto": task_def.auto,
            "properties": task_def.properties,
        }
        result.append(task_data)

    return Response(result)


@api_view(["GET"])
async def task_detail(request, task_id):
    """Get details of a specific task."""
    await engine.ensure_initialized()
    store = engine.get_store()

    task = await store.load_task(task_id)
    if not task:
        return Response({"error": f"Task '{task_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TaskInstanceSerializer(pydantic_to_dict(task))
    return Response(serializer.data)


@api_view(["POST"])
def task_complete(request, task_id):
    """Complete a pending task (for manual/human tasks in workflows).

    Human tasks use the auto:false convention - the task waits in READY state
    until this endpoint is called with the result data. The task definition
    properties contain the form schema (type, fields, etc.) that the UI reads
    to render the appropriate form.

    If the task definition has a JSON Schema in properties.schema, the result
    data is validated and coerced against it. Invalid data returns 400.
    """

    async def _load():
        await engine.ensure_initialized()
        store = engine.get_store()

        task = await store.load_task(task_id)
        if not task:
            return None, None, f"Task '{task_id}' not found"

        # Load process and definition for schema validation
        process = await store.load_process(task.process_id)
        if not process:
            return task, None, None  # No schema validation possible

        definition = await store.load_definition(process.definition_id)
        schema = None
        if definition:
            task_def = definition.tasks.get(task.task_definition_id)
            if task_def:
                schema = task_def.properties.get("schema")

        return task, schema, None

    task, schema, error = async_to_sync(_load)()
    if error:
        return Response({"error": error}, status=status.HTTP_404_NOT_FOUND)

    req_serializer = CompleteTaskRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result_data = req_serializer.validated_data.get("result", {})
        next_route = req_serializer.validated_data.get("next_route")

        # Validate against JSON Schema if present
        if schema and result_data:
            from zebra.forms import coerce_form_data, validate_form_data

            result_data = coerce_form_data(schema, result_data)
            validation_errors = validate_form_data(schema, result_data)
            if validation_errors:
                errors_by_field = {}
                for ve in validation_errors:
                    errors_by_field.setdefault(ve.field, []).append(ve.message)
                return Response(
                    {"error": "Validation failed", "field_errors": errors_by_field},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        async def _complete():
            wf_engine = engine.get_engine()
            result = TaskResult(success=True, output=result_data, next_route=next_route)
            new_tasks = await wf_engine.complete_task(task_id, result)
            return [
                {"id": t.id, "task_definition_id": t.task_definition_id, "state": t.state.value}
                for t in new_tasks
            ]

        new_tasks = async_to_sync(_complete)()

        # The completed task is deleted by the engine after routing,
        # so we return the completion result and any new tasks created.
        return Response(
            {
                "completed": True,
                "task_id": task_id,
                "result": result_data,
                "new_tasks": new_tasks,
            }
        )
    except Exception as e:
        logger.exception("Failed to complete task")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ===========================================================================
# Process Cancel / Delete
# ===========================================================================


@api_view(["POST"])
def process_cancel(request, process_id):
    """Cancel a running or paused process by failing it.

    Moves the process and all its non-terminal tasks to FAILED state.
    The process data is preserved for debugging.

    Request body (optional):
        {"reason": "Human-readable cancellation reason"}

    Returns:
        200: {"cancelled": true, "process_id": "...", "state": "failed"}
        404: Process not found
        409: Process is already in a terminal state
    """
    reason = "Cancelled by user"
    if request.data and isinstance(request.data, dict):
        reason = request.data.get("reason", reason)

    async def _cancel():
        await engine.ensure_initialized()
        wf_engine = engine.get_engine()
        return await wf_engine.fail_process(process_id, reason)

    try:
        process = async_to_sync(_cancel)()
        return Response(
            {
                "cancelled": True,
                "process_id": process.id,
                "state": process.state.value,
            }
        )
    except Exception as e:
        from zebra.core.exceptions import InvalidStateTransitionError, ProcessNotFoundError

        if isinstance(e, ProcessNotFoundError):
            return Response(
                {"error": f"Process '{process_id}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if isinstance(e, InvalidStateTransitionError):
            return Response(
                {"error": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        logger.exception("Failed to cancel process")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
def process_delete(request, process_id):
    """Hard-delete a process and all its tasks, FOEs, and locks.

    This is a destructive operation. The process data is removed permanently.
    Associated WorkflowRunModel (metrics) records are NOT deleted.

    Returns:
        200: {"deleted": true, "process_id": "..."}
        404: Process not found
    """

    async def _delete():
        await engine.ensure_initialized()
        store = engine.get_store()
        process = await store.load_process(process_id)
        if not process:
            return False
        return await store.delete_process(process_id)

    deleted = async_to_sync(_delete)()
    if not deleted:
        return Response(
            {"error": f"Process '{process_id}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({"deleted": True, "process_id": process_id})

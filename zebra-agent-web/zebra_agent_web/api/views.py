"""REST API views for Zebra Agent.

Provides async JSON API endpoints for:
- Agent operations (workflows, goals, runs)
- Execution monitoring (processes, tasks)
"""

import logging

from asgiref.sync import sync_to_async
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from zebra.core.models import TaskResult

from zebra_agent_web.api import agent_engine, engine
from zebra_agent_web.api.serializers import (
    WorkflowInfoSerializer,
    WorkflowDetailSerializer,
    WorkflowRunSerializer,
    AgentResultSerializer,
    WorkflowStatsSerializer,
    ExecuteGoalRequestSerializer,
    CreateWorkflowRequestSerializer,
    RateRunRequestSerializer,
    ProcessInstanceSerializer,
    ProcessInstanceListSerializer,
    ProcessInstanceDetailSerializer,
    TaskInstanceSerializer,
    CompleteTaskRequestSerializer,
)

logger = logging.getLogger(__name__)


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


@api_view(["POST"])
async def execute_goal(request):
    """Execute a goal using the agent loop."""
    await agent_engine.ensure_initialized()
    agent_loop = agent_engine.get_agent_loop()

    req_serializer = ExecuteGoalRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    goal = req_serializer.validated_data["goal"]

    try:
        result = await agent_loop.process_goal(goal)

        serializer = AgentResultSerializer(
            {
                "run_id": result.run_id,
                "workflow_name": result.workflow_name,
                "goal": result.goal,
                "output": result.output,
                "success": result.success,
                "tokens_used": result.tokens_used,
                "error": result.error,
                "created_new_workflow": result.created_new_workflow,
            }
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("Failed to execute goal")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
async def run_rate(request, run_id):
    """Rate a run."""
    await agent_engine.ensure_initialized()
    agent_loop = agent_engine.get_agent_loop()
    metrics = agent_engine.get_metrics()

    run = await metrics.get_run(run_id)
    if not run:
        return Response({"error": f"Run '{run_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

    req_serializer = RateRunRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    rating = req_serializer.validated_data["rating"]

    try:
        await agent_loop.record_rating(run_id, rating)
        return Response({"run_id": run_id, "rating": rating})
    except Exception as e:
        logger.exception("Failed to rate run")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# Execution monitoring endpoints (read-only + task completion)
# =============================================================================


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
async def task_complete(request, task_id):
    """Complete a pending task (for manual intervention in agent workflows)."""
    await engine.ensure_initialized()
    store = engine.get_store()
    wf_engine = engine.get_engine()

    task = await store.load_task(task_id)
    if not task:
        return Response({"error": f"Task '{task_id}' not found"}, status=status.HTTP_404_NOT_FOUND)

    req_serializer = CompleteTaskRequestSerializer(data=request.data)
    if not req_serializer.is_valid():
        return Response(req_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        result_data = req_serializer.validated_data.get("result", {})
        next_route = req_serializer.validated_data.get("next_route")

        result = TaskResult(success=True, output=result_data, next_route=next_route)
        await wf_engine.complete_task(task_id, result)

        # Reload task to get updated state
        task = await store.load_task(task_id)
        serializer = TaskInstanceSerializer(pydantic_to_dict(task))
        return Response(serializer.data)
    except Exception as e:
        logger.exception("Failed to complete task")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

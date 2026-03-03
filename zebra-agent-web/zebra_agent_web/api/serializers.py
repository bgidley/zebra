"""Serializers for Zebra Agent API responses.

These serialize the Pydantic models from zebra-py and zebra-agent to JSON for the REST API.
"""

from rest_framework import serializers

# =============================================================================
# Agent-specific serializers
# =============================================================================


class WorkflowInfoSerializer(serializers.Serializer):
    """Serializer for WorkflowInfo from zebra-agent."""

    name = serializers.CharField()
    description = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField())
    version = serializers.IntegerField()
    use_when = serializers.CharField(allow_null=True, required=False)
    success_rate = serializers.FloatField()
    use_count = serializers.IntegerField()


class WorkflowDetailSerializer(WorkflowInfoSerializer):
    """Detailed workflow info including YAML content."""

    yaml_content = serializers.CharField()
    stats = serializers.DictField()


class WorkflowRunSerializer(serializers.Serializer):
    """Serializer for WorkflowRun from zebra-agent."""

    id = serializers.CharField()
    workflow_name = serializers.CharField()
    goal = serializers.CharField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    success = serializers.BooleanField()
    user_rating = serializers.IntegerField(allow_null=True)
    tokens_used = serializers.IntegerField()
    error = serializers.CharField(allow_null=True)
    output = serializers.JSONField(allow_null=True)


class AgentResultSerializer(serializers.Serializer):
    """Serializer for AgentResult from zebra-agent."""

    run_id = serializers.CharField()
    workflow_name = serializers.CharField()
    goal = serializers.CharField()
    output = serializers.JSONField(allow_null=True)
    success = serializers.BooleanField()
    tokens_used = serializers.IntegerField()
    error = serializers.CharField(allow_null=True)
    created_new_workflow = serializers.BooleanField()


class GoalAcceptedSerializer(serializers.Serializer):
    """Response serializer for accepted (async) goal execution."""

    run_id = serializers.CharField()
    status = serializers.CharField()
    message = serializers.CharField()
    status_url = serializers.CharField()


class WorkflowStatsSerializer(serializers.Serializer):
    """Serializer for workflow statistics."""

    total_runs = serializers.IntegerField()
    successful_runs = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_rating = serializers.FloatField(allow_null=True)
    last_used = serializers.DateTimeField(allow_null=True)


# =============================================================================
# Request serializers
# =============================================================================


class ExecuteGoalRequestSerializer(serializers.Serializer):
    """Request serializer for executing a goal."""

    goal = serializers.CharField(help_text="The goal to accomplish")


class CreateWorkflowRequestSerializer(serializers.Serializer):
    """Request serializer for creating a workflow from YAML."""

    yaml_content = serializers.CharField(help_text="YAML workflow definition")


class RateRunRequestSerializer(serializers.Serializer):
    """Request serializer for rating a run."""

    rating = serializers.IntegerField(min_value=1, max_value=5)


# =============================================================================
# Execution monitoring serializers (subset from zebra-web)
# =============================================================================


class TaskInstanceSerializer(serializers.Serializer):
    """Serializer for TaskInstance."""

    id = serializers.CharField()
    process_id = serializers.CharField()
    task_definition_id = serializers.CharField()
    state = serializers.CharField()
    foe_id = serializers.CharField()
    properties = serializers.DictField()
    result = serializers.DictField(allow_null=True)
    error = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class ProcessInstanceSerializer(serializers.Serializer):
    """Serializer for ProcessInstance."""

    id = serializers.CharField()
    definition_id = serializers.CharField()
    state = serializers.CharField()
    properties = serializers.DictField()
    parent_process_id = serializers.CharField(allow_null=True)
    parent_task_id = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class ProcessInstanceListSerializer(serializers.Serializer):
    """Lightweight serializer for listing processes."""

    id = serializers.CharField()
    definition_id = serializers.CharField()
    definition_name = serializers.CharField(required=False)
    state = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class TaskDefinitionSerializer(serializers.Serializer):
    """Serializer for TaskDefinition."""

    id = serializers.CharField()
    name = serializers.CharField()
    auto = serializers.BooleanField()
    synchronized = serializers.BooleanField()
    action = serializers.CharField(allow_null=True)
    properties = serializers.DictField()


class ProcessDefinitionSerializer(serializers.Serializer):
    """Serializer for ProcessDefinition."""

    id = serializers.CharField()
    name = serializers.CharField()
    version = serializers.IntegerField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    first_task_id = serializers.CharField()
    tasks = serializers.DictField(child=TaskDefinitionSerializer())


class FlowOfExecutionSerializer(serializers.Serializer):
    """Serializer for FlowOfExecution."""

    id = serializers.CharField()
    process_id = serializers.CharField()
    parent_foe_id = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class ProcessInstanceDetailSerializer(ProcessInstanceSerializer):
    """Detailed serializer for ProcessInstance including tasks and FOEs."""

    tasks = TaskInstanceSerializer(many=True, required=False)
    foes = FlowOfExecutionSerializer(many=True, required=False)
    definition = ProcessDefinitionSerializer(required=False)


class CompleteTaskRequestSerializer(serializers.Serializer):
    """Request serializer for completing a pending task."""

    result = serializers.DictField(required=False, default=dict)
    next_route = serializers.CharField(required=False, allow_null=True)

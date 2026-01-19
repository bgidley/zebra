"""Serializers for Zebra API responses.

These serialize the Pydantic models from zebra-py to JSON for the REST API.
"""

from rest_framework import serializers


class TaskDefinitionSerializer(serializers.Serializer):
    """Serializer for TaskDefinition."""

    id = serializers.CharField()
    name = serializers.CharField()
    auto = serializers.BooleanField()
    synchronized = serializers.BooleanField()
    action = serializers.CharField(allow_null=True)
    properties = serializers.DictField()


class RoutingDefinitionSerializer(serializers.Serializer):
    """Serializer for RoutingDefinition."""

    id = serializers.CharField()
    source_task_id = serializers.CharField()
    dest_task_id = serializers.CharField()
    parallel = serializers.BooleanField()
    condition = serializers.CharField(allow_null=True)


class ProcessDefinitionSerializer(serializers.Serializer):
    """Serializer for ProcessDefinition."""

    id = serializers.CharField()
    name = serializers.CharField()
    version = serializers.IntegerField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    first_task_id = serializers.CharField()
    tasks = serializers.DictField(child=TaskDefinitionSerializer())
    routings = RoutingDefinitionSerializer(many=True)


class ProcessDefinitionListSerializer(serializers.Serializer):
    """Lightweight serializer for listing definitions."""

    id = serializers.CharField()
    name = serializers.CharField()
    version = serializers.IntegerField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    task_count = serializers.SerializerMethodField()

    def get_task_count(self, obj):
        if isinstance(obj, dict):
            return len(obj.get("tasks", {}))
        return len(obj.tasks) if hasattr(obj, "tasks") else 0


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


class FlowOfExecutionSerializer(serializers.Serializer):
    """Serializer for FlowOfExecution."""

    id = serializers.CharField()
    process_id = serializers.CharField()
    parent_foe_id = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


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


class ProcessInstanceDetailSerializer(ProcessInstanceSerializer):
    """Detailed serializer for ProcessInstance including tasks and FOEs."""

    tasks = TaskInstanceSerializer(many=True, required=False)
    foes = FlowOfExecutionSerializer(many=True, required=False)
    definition = ProcessDefinitionSerializer(required=False)


class ProcessInstanceListSerializer(serializers.Serializer):
    """Lightweight serializer for listing processes."""

    id = serializers.CharField()
    definition_id = serializers.CharField()
    definition_name = serializers.CharField(required=False)
    state = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


# Request serializers


class CreateDefinitionRequestSerializer(serializers.Serializer):
    """Request serializer for creating a definition from YAML."""

    yaml_content = serializers.CharField(help_text="YAML workflow definition")


class StartProcessRequestSerializer(serializers.Serializer):
    """Request serializer for starting a new process."""

    definition_id = serializers.CharField()
    properties = serializers.DictField(required=False, default=dict)


class CompleteTaskRequestSerializer(serializers.Serializer):
    """Request serializer for completing a pending task."""

    result = serializers.DictField(required=False, default=dict)
    next_route = serializers.CharField(required=False, allow_null=True)

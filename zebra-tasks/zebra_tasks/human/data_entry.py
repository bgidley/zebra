"""DataEntryAction - Request structured data input from a human."""

from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction


class DataEntryAction(TaskAction):
    """
    TaskAction that requests structured data entry from a human.

    This action starts the task and puts it in a waiting state until
    an external system (UI, API, etc.) calls engine.complete_task()
    with the collected data.

    Properties:
        title: Title for the data entry form
        fields: List of field definitions with:
            - name: Field identifier (required)
            - label: Human-readable label (required)
            - type: Field type - "text", "number", "boolean", "date", "select" (default: "text")
            - required: Whether field is required (default: False)
            - default: Default value (optional)
            - description: Help text (optional)
            - options: List of options for "select" type (optional)
        output_key: Where to store collected data (default: "user_input")
        timeout: Optional timeout in seconds (not enforced by action)

    The task will wait in RUNNING state until completed externally.
    External completion should provide data matching the field schema.

    Example workflow usage:
        ```yaml
        tasks:
          get_user_info:
            name: "Collect User Information"
            action: data_entry
            auto: true
            properties:
              title: "User Registration"
              fields:
                - name: username
                  label: "Username"
                  type: text
                  required: true
                - name: age
                  label: "Age"
                  type: number
                  required: true
                - name: email
                  label: "Email Address"
                  type: text
                  required: false
                - name: subscribe
                  label: "Subscribe to newsletter"
                  type: boolean
                  default: true
              output_key: user_data

          process_info:
            name: "Process User Data"
            action: llm_call
            properties:
              prompt: "Process this user data: {{user_data}}"
        ```

    External completion example:
        ```python
        # From UI or API handler:
        result = TaskResult.ok(output={
            "username": "john_doe",
            "age": 30,
            "email": "john@example.com",
            "subscribe": True
        })
        await engine.complete_task(task_id, result)
        ```
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Initialize data entry and wait for external completion."""
        # Validate required properties
        title = task.properties.get("title", "Data Entry")
        fields = task.properties.get("fields", [])

        if not fields:
            return TaskResult.fail("No fields defined for data entry")

        # Validate field definitions
        validation_error = self._validate_fields(fields)
        if validation_error:
            return TaskResult.fail(f"Invalid field definition: {validation_error}")

        # Store the data entry request in task properties for external systems
        # This allows UI/API to retrieve the form schema
        context.set_process_property(f"__data_entry_{task.id}__", {
            "title": title,
            "fields": fields,
            "task_id": task.id,
            "status": "waiting",
        })

        # Return a special result that indicates waiting for external input
        # The task will remain in RUNNING state until engine.complete_task() is called
        return TaskResult(
            success=True,
            output={"status": "waiting_for_input", "title": title, "fields": fields},
            error=None,
        )

    def _validate_fields(self, fields: list[dict[str, Any]]) -> str | None:
        """Validate field definitions."""
        valid_types = {"text", "number", "boolean", "date", "select"}

        for i, field in enumerate(fields):
            if not isinstance(field, dict):
                return f"Field {i} is not a dictionary"

            if "name" not in field:
                return f"Field {i} missing required 'name'"

            if "label" not in field:
                return f"Field {i} ({field.get('name')}) missing required 'label'"

            field_type = field.get("type", "text")
            if field_type not in valid_types:
                return f"Field {field['name']} has invalid type '{field_type}'"

            if field_type == "select" and "options" not in field:
                return f"Field {field['name']} with type 'select' must have 'options'"

        return None

    async def on_construct(self, task: TaskInstance, context: ExecutionContext) -> None:
        """Called before task execution."""
        # Mark that this task is waiting for human input
        context.set_process_property(f"__waiting_for_human_{task.id}__", True)

    async def on_destruct(self, task: TaskInstance, context: ExecutionContext) -> None:
        """Called after task completion."""
        # Clean up waiting flag and data entry metadata
        context.process.properties.pop(f"__waiting_for_human_{task.id}__", None)
        context.process.properties.pop(f"__data_entry_{task.id}__", None)

        # Store the collected data in the specified output key
        if task.result and isinstance(task.result, dict):
            output_key = task.properties.get("output_key", "user_input")
            context.set_process_property(output_key, task.result)

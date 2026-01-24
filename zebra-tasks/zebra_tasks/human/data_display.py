"""DataDisplayAction - Display structured data to a human and wait for acknowledgment."""

from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction


class DataDisplayAction(TaskAction):
    """
    TaskAction that displays structured data to a human and waits for acknowledgment.

    This action starts the task and puts it in a waiting state until
    an external system (UI, API, etc.) calls engine.complete_task()
    to acknowledge the display was viewed.

    Properties:
        title: Title for the display (required)
        message: Main message or description text (optional)
        fields: List of field data to display with:
            - label: Field label (required)
            - value: Field value (required, supports {{var}} templates)
            - format: Display format hint - "text", "number", "currency", "date",
                      "code" (default: "text")
        data: Alternative to fields - raw dict of data to display (optional)
        output_key: Where to store acknowledgment info (default: "display_acknowledged")
        require_confirmation: If true, expect explicit confirmation (default: False)
        timeout: Optional timeout in seconds (not enforced by action)

    The task will wait in RUNNING state until acknowledged externally.
    External acknowledgment should call engine.complete_task() with optional feedback.

    Example workflow usage:
        ```yaml
        tasks:
          analyze_data:
            name: "Analyze Data"
            action: llm_call
            properties:
              prompt: "Analyze: {{input_data}}"
              output_key: analysis

          show_results:
            name: "Display Analysis Results"
            action: data_display
            auto: true
            properties:
              title: "Analysis Complete"
              message: "Here are the results of the data analysis."
              fields:
                - label: "Analysis Type"
                  value: "{{analysis.type}}"
                - label: "Confidence Score"
                  value: "{{analysis.confidence}}"
                  format: "number"
                - label: "Recommendation"
                  value: "{{analysis.recommendation}}"
              require_confirmation: true
              output_key: user_acknowledged

          next_step:
            name: "Continue Processing"
            action: some_action
        ```

    External acknowledgment example:
        ```python
        # From UI or API handler (simple acknowledgment):
        result = TaskResult.ok(output={"acknowledged": True})
        await engine.complete_task(task_id, result)

        # With feedback:
        result = TaskResult.ok(output={
            "acknowledged": True,
            "feedback": "Looks good, proceed",
            "rating": 5
        })
        await engine.complete_task(task_id, result)
        ```
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Initialize data display and wait for acknowledgment."""
        # Get properties
        title = task.properties.get("title")
        if not title:
            return TaskResult.fail("No title provided for data display")

        message = task.properties.get("message", "")
        fields = task.properties.get("fields", [])
        data = task.properties.get("data")
        require_confirmation = task.properties.get("require_confirmation", False)

        # Need either fields or data
        if not fields and not data:
            return TaskResult.fail("No fields or data provided for display")

        # Resolve templates in fields
        resolved_fields = []
        if fields:
            for field in fields:
                if not isinstance(field, dict):
                    return TaskResult.fail(f"Invalid field definition: {field}")

                if "label" not in field or "value" not in field:
                    return TaskResult.fail(
                        f"Field missing required 'label' or 'value': {field}"
                    )

                resolved_value = field["value"]
                if isinstance(resolved_value, str):
                    resolved_value = context.resolve_template(resolved_value)

                resolved_fields.append({
                    "label": field["label"],
                    "value": resolved_value,
                    "format": field.get("format", "text"),
                })

        # Resolve templates in message
        if message and isinstance(message, str):
            message = context.resolve_template(message)

        # Resolve templates in data dict values
        resolved_data = None
        if data:
            resolved_data = self._resolve_data_templates(data, context)

        # Store the display request in process properties for external systems
        display_info = {
            "title": title,
            "message": message,
            "fields": resolved_fields,
            "data": resolved_data,
            "require_confirmation": require_confirmation,
            "task_id": task.id,
            "status": "waiting_acknowledgment",
        }

        context.set_process_property(f"__data_display_{task.id}__", display_info)

        # Return result indicating waiting for acknowledgment
        return TaskResult(
            success=True,
            output={
                "status": "waiting_acknowledgment",
                "title": title,
                "message": message,
                "fields": resolved_fields,
                "data": resolved_data,
                "require_confirmation": require_confirmation,
            },
            error=None,
        )

    def _resolve_data_templates(
        self, data: Any, context: ExecutionContext
    ) -> Any:
        """Recursively resolve templates in data structure."""
        if isinstance(data, str):
            return context.resolve_template(data)
        elif isinstance(data, dict):
            return {k: self._resolve_data_templates(v, context) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_data_templates(item, context) for item in data]
        else:
            return data

    async def on_construct(self, task: TaskInstance, context: ExecutionContext) -> None:
        """Called before task execution."""
        # Mark that this task is waiting for human acknowledgment
        context.set_process_property(f"__waiting_for_human_{task.id}__", True)

    async def on_destruct(self, task: TaskInstance, context: ExecutionContext) -> None:
        """Called after task completion."""
        # Clean up waiting flag and display metadata
        context.process.properties.pop(f"__waiting_for_human_{task.id}__", None)
        context.process.properties.pop(f"__data_display_{task.id}__", None)

        # Store the acknowledgment result in the specified output key
        if task.result:
            output_key = task.properties.get("output_key", "display_acknowledged")
            acknowledgment = task.result if isinstance(task.result, dict) else {
                "acknowledged": True,
                "result": task.result,
            }
            context.set_process_property(output_key, acknowledgment)

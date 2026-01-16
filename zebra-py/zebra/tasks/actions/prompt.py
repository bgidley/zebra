"""Prompt task action for human/AI input.

This is a key action for Claude integration - it pauses execution
and waits for external input before continuing.
"""

from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction


class PromptTaskAction(TaskAction):
    """Pause execution and wait for external input with validation.

    This action is designed for integration with Claude or human operators.
    When executed, it marks the task as READY and waits for the task to
    be completed externally via engine.complete_task().

    Properties:
        prompt: The prompt/question to display (required)
        input_type: Type of input expected (text, number, boolean, choice, multi_choice)
        schema: Optional JSON schema for validation
        options: List of valid choices (for choice/multi_choice types)
        required: If true, input is mandatory (no empty values)
        default: Optional default value
        help: Optional help text for the user
        output_key: Optional key to store result in process properties
        validation_error: Custom error message for validation failures

    Usage:
        1. Workflow reaches a prompt task
        2. Task enters READY state with prompt in properties
        3. External system (Claude/human) retrieves pending tasks
        4. External system calls engine.complete_task(task_id, result)
        5. Workflow continues with the provided result

    Example workflow definition:
        tasks:
          get_name:
            name: "Get Name"
            action: prompt
            auto: false
            properties:
              prompt: "What is your name?"
              input_type: text
              required: true
              output_key: user_name

          get_age:
            name: "Get Age"
            action: prompt
            auto: false
            properties:
              prompt: "How old are you, {{user_name}}?"
              input_type: number
              schema:
                minimum: 0
                maximum: 150
              output_key: user_age

          get_preference:
            name: "Get Preference"
            action: prompt
            auto: false
            properties:
              prompt: "How do you prefer to be contacted?"
              input_type: choice
              options:
                - value: email
                  label: "Email"
                - value: phone
                  label: "Phone"
              output_key: contact_preference
    """

    VALID_INPUT_TYPES = {"text", "number", "boolean", "choice", "multi_choice"}

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        props = context.task_definition.properties

        # Get configuration
        prompt = task.properties.get("prompt") or props.get("prompt", "Please provide input:")
        prompt = context.resolve_template(prompt)

        input_type = props.get("input_type", "text")
        schema = props.get("schema")
        options = props.get("options", [])
        required = props.get("required", False)
        default = props.get("default")
        help_text = props.get("help")
        output_key = props.get("output_key")
        validation_error = props.get("validation_error")

        # Validate input_type
        if input_type not in self.VALID_INPUT_TYPES:
            return TaskResult.fail(
                f"Invalid input_type '{input_type}'. Must be one of: {self.VALID_INPUT_TYPES}"
            )

        # Store metadata for external systems
        task.properties["__prompt__"] = prompt
        task.properties["__input_type__"] = input_type
        task.properties["__options__"] = options
        task.properties["__schema__"] = schema
        task.properties["__help__"] = help_text
        task.properties["__required__"] = required

        # Check for existing result (task being re-run after completion)
        if task.result is not None:
            return TaskResult.ok(task.result)

        # Check for pre-provided input
        provided_input = task.properties.get("input")
        if provided_input is not None:
            # Validate the input
            validated, error = self._validate_input(
                provided_input, input_type, schema, options, required, validation_error
            )
            if error:
                return TaskResult.fail(error)

            result = self._build_result(prompt, validated, output_key, context)
            return TaskResult.ok(result)

        # No input - check default
        if default is not None:
            validated, error = self._validate_input(
                default, input_type, schema, options, required, validation_error
            )
            if error:
                return TaskResult.fail(f"Invalid default value: {error}")

            result = self._build_result(prompt, validated, output_key, context)
            return TaskResult.ok(result)

        # No input and no default - return awaiting state
        return TaskResult.ok({
            "prompt": prompt,
            "input_type": input_type,
            "options": options,
            "help": help_text,
            "required": required,
            "response": None,
            "awaiting_input": True,
        })

    def _validate_input(
        self,
        value: Any,
        input_type: str,
        schema: dict | None,
        options: list,
        required: bool,
        custom_error: str | None,
    ) -> tuple[Any, str | None]:
        """Validate input against type and schema.

        Returns:
            Tuple of (validated_value, error_message).
            If validation passes, error_message is None.
        """
        # Check required
        if required and (value is None or value == ""):
            return None, custom_error or "This field is required"

        # Allow empty values for non-required fields
        if value is None or value == "":
            return value, None

        # Type-specific validation and conversion
        if input_type == "number":
            try:
                if isinstance(value, (int, float)):
                    pass
                elif isinstance(value, str):
                    value = float(value) if "." in value else int(value)
                else:
                    return None, custom_error or "Invalid number"
            except (ValueError, TypeError):
                return None, custom_error or "Invalid number"

        elif input_type == "boolean":
            if isinstance(value, bool):
                pass
            elif isinstance(value, str):
                lower = value.lower()
                if lower in ("true", "yes", "y", "1"):
                    value = True
                elif lower in ("false", "no", "n", "0"):
                    value = False
                else:
                    return None, custom_error or "Invalid boolean (use yes/no or true/false)"
            elif isinstance(value, (int, float)):
                value = bool(value)
            else:
                return None, custom_error or "Invalid boolean"

        elif input_type == "choice":
            valid_values = self._get_option_values(options)
            if value not in valid_values:
                return None, custom_error or f"Invalid choice. Options: {valid_values}"

        elif input_type == "multi_choice":
            if not isinstance(value, list):
                value = [value]
            valid_values = self._get_option_values(options)
            for v in value:
                if v not in valid_values:
                    return None, custom_error or f"Invalid choice: {v}. Options: {valid_values}"

        # JSON Schema validation (if jsonschema available)
        if schema:
            error = self._validate_schema(value, schema, custom_error)
            if error:
                return None, error

        return value, None

    def _get_option_values(self, options: list) -> list:
        """Extract values from options list (handles both simple and dict formats)."""
        return [o["value"] if isinstance(o, dict) else o for o in options]

    def _validate_schema(self, value: Any, schema: dict, custom_error: str | None) -> str | None:
        """Validate value against JSON schema."""
        try:
            import jsonschema
            jsonschema.validate(value, schema)
            return None
        except ImportError:
            # jsonschema not installed, skip validation
            return None
        except Exception as e:
            # Handle validation errors
            if hasattr(e, "message"):
                return custom_error or str(e.message)
            return custom_error or str(e)

    def _build_result(
        self,
        prompt: str,
        value: Any,
        output_key: str | None,
        context: ExecutionContext,
    ) -> dict:
        """Build the result and optionally store in process properties."""
        if output_key:
            context.set_process_property(output_key, value)

        return {"prompt": prompt, "response": value}


class DecisionTaskAction(TaskAction):
    """Present options and route based on selection.

    A specialized prompt that routes to different tasks based on
    the selected option. Works with RouteNameCondition.

    Properties:
        prompt: The decision prompt
        options: List of option names (matching routing names)

    Example:
        tasks:
          decide_approach:
            name: "Choose Approach"
            action: decision
            auto: false
            properties:
              prompt: "How should we proceed?"
              options:
                - "quick_fix"
                - "full_refactor"
                - "skip"

        routings:
          - from: decide_approach
            to: quick_fix_task
            name: quick_fix
            condition: route_name
          - from: decide_approach
            to: refactor_task
            name: full_refactor
            condition: route_name
          - from: decide_approach
            to: skip_task
            name: skip
            condition: route_name
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        prompt = task.properties.get("prompt") or context.task_definition.properties.get(
            "prompt", "Please select an option:"
        )
        options = context.task_definition.properties.get("options", [])

        prompt = context.resolve_template(prompt)

        # Check for pre-provided selection
        selection = task.properties.get("selection")
        if selection is not None:
            if selection in options:
                return TaskResult(success=True, output=selection, next_route=selection)
            else:
                return TaskResult.fail(
                    f"Invalid selection '{selection}'. Valid options: {options}"
                )

        # Store options for external UI
        task.properties["__prompt__"] = prompt
        task.properties["__options__"] = options

        # Check default
        default = context.task_definition.properties.get("default")
        if default is not None and default in options:
            return TaskResult(success=True, output=default, next_route=default)

        # Awaiting selection
        return TaskResult.ok({
            "prompt": prompt,
            "options": options,
            "awaiting_input": True,
        })

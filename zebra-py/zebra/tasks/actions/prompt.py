"""Prompt task action for human/AI input.

This is a key action for Claude integration - it pauses execution
and waits for external input before continuing.
"""

from zebra.core.models import TaskInstance, TaskResult, TaskState
from zebra.tasks.base import ExecutionContext, TaskAction


class PromptTaskAction(TaskAction):
    """Pause execution and wait for external input.

    This action is designed for integration with Claude or human operators.
    When executed, it marks the task as READY and waits for the task to
    be completed externally via engine.complete_task().

    Properties:
        prompt: The prompt/question to display (required)
        schema: Optional JSON schema for structured responses
        default: Optional default value

    Usage:
        1. Workflow reaches a prompt task
        2. Task enters READY state with prompt in properties
        3. External system (Claude/human) retrieves pending tasks
        4. External system calls engine.complete_task(task_id, result)
        5. Workflow continues with the provided result

    Example workflow definition:
        tasks:
          get_requirements:
            name: "Gather Requirements"
            action: prompt
            auto: false  # Important: must be manual for prompts
            properties:
              prompt: "What feature should we implement?"

          confirm_plan:
            name: "Confirm Plan"
            action: prompt
            auto: false
            properties:
              prompt: "Does this plan look correct? {{plan.output}}"
              schema:
                type: object
                properties:
                  approved:
                    type: boolean
                  feedback:
                    type: string
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        prompt = task.properties.get("prompt") or context.task_definition.properties.get(
            "prompt", "Please provide input:"
        )

        # Resolve any template variables in the prompt
        prompt = context.resolve_template(prompt)

        # Check if we already have a response (task being re-run after completion)
        if task.result is not None:
            return TaskResult.ok(task.result)

        # Store the prompt in task properties for external systems to read
        task.properties["__prompt__"] = prompt
        task.properties["__schema__"] = context.task_definition.properties.get("schema")

        # Mark as awaiting input by NOT completing the task
        # The task will stay in RUNNING state and be handled externally
        # We return a special result that tells the engine to wait

        # Actually, we need a different approach - we should set the task
        # to a state where it waits for completion. Since run() is expected
        # to complete the task, we need to signal that this is a "pause" point.

        # For prompt tasks, we DO NOT return TaskResult.ok() - instead we
        # leave the task in a non-completed state. The calling code in
        # engine._run_task() will see task.state != COMPLETE and stop.

        # But wait - we need to somehow NOT auto-complete. Let's check if
        # there's input already provided via task properties.

        provided_input = task.properties.get("input")
        if provided_input is not None:
            # Input was provided, complete with it
            return TaskResult.ok({"prompt": prompt, "response": provided_input})

        # No input - this is where we need to pause.
        # We'll use a convention: if auto=false, the task waits in READY
        # state for external completion. The engine already handles this.

        # For auto=true prompt tasks (unusual but possible), we return
        # the default value if specified
        default = context.task_definition.properties.get("default")
        if default is not None:
            return TaskResult.ok({"prompt": prompt, "response": default})

        # No default and auto=true - this is a config error for prompts
        # But we'll be lenient and just return the prompt without a response
        return TaskResult.ok({"prompt": prompt, "response": None, "awaiting_input": True})


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

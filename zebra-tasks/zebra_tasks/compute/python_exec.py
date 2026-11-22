"""Python code execution action."""

import ast
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.compute.sandbox import (
    ALLOWED_MODULES,
    BLOCKED_BUILTINS,
    build_globals,
    failure_appendix,
)


class PythonExecAction(TaskAction):
    """
    Execute Python code and capture the result.

    This action executes Python code in a restricted environment,
    capturing both the return value and any printed output.

    Properties:
        code: Python code to execute (supports {{var}} templates)
        timeout: Maximum execution time in seconds (default: 30)
        output_key: Where to store result (default: "result")
        capture_prints: Whether to capture print output (default: True)

    The code can:
        - Use standard library modules (math, json, datetime, etc.)
        - Access process properties via `props` dict
        - Return a value by assigning to `result` variable
        - Print output (captured in `output` field)

    Example workflow usage:
        ```yaml
        tasks:
          calculate:
            name: "Calculate result"
            action: python_exec
            auto: true
            properties:
              code: |
                import math
                numbers = [1, 2, 3, 4, 5]
                result = {
                    "sum": sum(numbers),
                    "mean": sum(numbers) / len(numbers),
                    "sqrt_sum": math.sqrt(sum(numbers))
                }
              output_key: calculation
        ```

    Security note:
        Code runs in the same process with limited restrictions (a restricted execution
        contract, not isolation). Do not execute untrusted code. The contract (allowed
        modules, blocked builtins, ``props`` / ``result``) is defined in
        ``zebra_tasks.compute.sandbox``.
    """

    # #245: writes outside this run; judged at runtime, refused by strict gym
    reversibility_hint = "context_dependent"

    description = (
        "Execute Python code in a restricted environment and capture the result. "
        "Allowed imports, blocked builtins and the result rule: zebra_tasks.compute.sandbox."
    )

    inputs = [
        ParameterDef(
            name="code",
            type="string",
            description="Python code to execute (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="timeout",
            type="int",
            description="Maximum execution time in seconds (not strictly enforced)",
            required=False,
            default=30,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="result",
        ),
        ParameterDef(
            name="capture_prints",
            type="bool",
            description="Whether to capture print statements",
            required=False,
            default=True,
        ),
    ]

    outputs = [
        ParameterDef(
            name="result",
            type="any",
            description="The value assigned to 'result' variable in the code",
            required=False,
        ),
        ParameterDef(
            name="stdout",
            type="string",
            description="Captured standard output from print statements",
            required=True,
        ),
        ParameterDef(
            name="stderr",
            type="string",
            description="Captured standard error output",
            required=True,
        ),
    ]

    # The contract lives in zebra_tasks.compute.sandbox (#323)
    ALLOWED_MODULES = ALLOWED_MODULES
    BLOCKED_BUILTINS = BLOCKED_BUILTINS

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute Python code."""
        code = task.properties.get("code")
        if not code:
            return TaskResult.fail("No code provided")

        # Resolve templates in code
        code = context.resolve_template(code)

        output_key = task.properties.get("output_key", "result")
        capture_prints = task.properties.get("capture_prints", True)

        try:
            # Validate code syntax
            try:
                ast.parse(code)
            except SyntaxError as e:
                return TaskResult.fail(f"Syntax error: {e}")

            # Build execution environment
            exec_globals = self._build_globals(context)
            exec_locals = {"result": None}

            # Capture output
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            # Execute code
            if capture_prints:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    exec(code, exec_globals, exec_locals)
            else:
                exec(code, exec_globals, exec_locals)

            # Get result
            result = exec_locals.get("result")
            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()

            # Store result in process properties
            context.set_process_property(output_key, result)

            # Also store output if any
            if stdout_output:
                context.set_process_property(f"{output_key}_stdout", stdout_output)

            return TaskResult.ok(
                output={
                    "result": result,
                    "stdout": stdout_output,
                    "stderr": stderr_output,
                }
            )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            tb = traceback.format_exc()
            return TaskResult.fail(f"Execution error: {error_msg}\n{tb}{failure_appendix(e)}")

    def _build_globals(self, context: ExecutionContext) -> dict[str, Any]:
        """Build the global namespace for code execution."""
        return build_globals(context.process.properties)

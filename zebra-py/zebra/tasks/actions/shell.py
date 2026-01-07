"""Shell command task action."""

import asyncio
import shlex
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction


class ShellTaskAction(TaskAction):
    """Execute a shell command.

    Properties:
        command: The shell command to execute (required)
        cwd: Working directory (optional)
        timeout: Command timeout in seconds (default: 300)
        capture_output: Whether to capture stdout/stderr (default: True)
        shell: Whether to run through shell (default: True)

    Result:
        - output.stdout: Standard output
        - output.stderr: Standard error
        - output.returncode: Exit code

    Example workflow definition:
        tasks:
          run_tests:
            name: "Run Tests"
            action: shell
            properties:
              command: "pytest tests/"
              timeout: 600
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        command = task.properties.get("command")
        if not command:
            command = context.task_definition.properties.get("command")

        if not command:
            return TaskResult.fail("No 'command' property specified")

        # Resolve any template variables
        command = context.resolve_template(command)

        cwd = task.properties.get("cwd") or context.task_definition.properties.get("cwd")
        if cwd:
            cwd = context.resolve_template(cwd)

        timeout = task.properties.get("timeout") or context.task_definition.properties.get(
            "timeout", 300
        )
        capture_output = task.properties.get("capture_output", True)
        use_shell = task.properties.get("shell", True)

        try:
            if use_shell:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE if capture_output else None,
                    stderr=asyncio.subprocess.PIPE if capture_output else None,
                    cwd=cwd,
                )
            else:
                args = shlex.split(command)
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE if capture_output else None,
                    stderr=asyncio.subprocess.PIPE if capture_output else None,
                    cwd=cwd,
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return TaskResult.fail(f"Command timed out after {timeout} seconds")

            output: dict[str, Any] = {
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
            }

            if proc.returncode == 0:
                return TaskResult.ok(output)
            else:
                return TaskResult(
                    success=False,
                    output=output,
                    error=f"Command exited with code {proc.returncode}",
                )

        except Exception as e:
            return TaskResult.fail(f"Failed to execute command: {e}")

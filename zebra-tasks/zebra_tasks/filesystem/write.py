"""File write action for workflow tasks."""

import base64

import aiofiles
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    PathExistsError,
    validate_path,
)


class FileWriteAction(TaskAction):
    """Write content to a file.

    This action writes content to a file, optionally creating parent
    directories and supporting append mode.

    Properties:
        path: File path to write (supports {{var}} templates)
        content: Content to write (supports {{var}} templates)
        encoding: Text encoding (default: "utf-8")
        mode: "write" (overwrite) or "append" (default: "write")
        binary: If True, content is base64-encoded and will be decoded
        create_dirs: Create parent directories if missing (default: True)
        overwrite: Allow overwriting existing files (default: True)
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          write_report:
            name: "Write analysis report"
            action: file_write
            auto: true
            properties:
              path: "output/report.txt"
              content: |
                Analysis Results
                ================
                Input: {{input_file}}
                Result: {{analysis_result}}
              create_dirs: true
        ```

    Output:
        - success: True if file was written successfully
        - output.path: The resolved file path
        - output.bytes_written: Number of bytes written
        - output.mode: Write mode used
    """

    description = "Write content to a file, with options for append mode and directory creation."

    inputs = [
        ParameterDef(
            name="path",
            type="string",
            description="File path to write (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="content",
            type="string",
            description="Content to write (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="encoding",
            type="string",
            description="Text encoding for writing the file",
            required=False,
            default="utf-8",
        ),
        ParameterDef(
            name="mode",
            type="string",
            description="Write mode: 'write' (overwrite) or 'append'",
            required=False,
            default="write",
        ),
        ParameterDef(
            name="binary",
            type="bool",
            description="If True, content is base64-encoded and will be decoded before writing",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="create_dirs",
            type="bool",
            description="Create parent directories if they don't exist",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="overwrite",
            type="bool",
            description="Allow overwriting existing files",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="base_directory",
            type="string",
            description="Sandbox directory for security (paths must be within)",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="path",
            type="string",
            description="The resolved file path",
            required=True,
        ),
        ParameterDef(
            name="bytes_written",
            type="int",
            description="Number of bytes written",
            required=True,
        ),
        ParameterDef(
            name="mode",
            type="string",
            description="Write mode used ('write' or 'append')",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Write content to file."""
        # Get and validate path
        path_template = task.properties.get("path")
        if not path_template:
            return TaskResult.fail("No path provided")

        content_template = task.properties.get("content")
        if content_template is None:
            return TaskResult.fail("No content provided")

        path_str = context.resolve_template(path_template)
        content = context.resolve_template(str(content_template))

        encoding = task.properties.get("encoding", "utf-8")
        mode = task.properties.get("mode", "write")
        binary = task.properties.get("binary", False)
        create_dirs = task.properties.get("create_dirs", True)
        overwrite = task.properties.get("overwrite", True)

        # Validate mode
        if mode not in ("write", "append"):
            return TaskResult.fail(f"Invalid mode: {mode}. Use 'write' or 'append'.")

        # Build config from properties
        config = FileSystemConfig.from_properties(task.properties)

        try:
            # Validate path (don't require existence)
            resolved_path = validate_path(path_str, config, must_exist=False)

            # Check if file exists when overwrite is disabled
            if not overwrite and resolved_path.exists() and mode == "write":
                raise PathExistsError(f"File already exists and overwrite=False: {resolved_path}")

            # Create parent directories if needed
            if create_dirs:
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
            elif not resolved_path.parent.exists():
                return TaskResult.fail(
                    f"Parent directory does not exist: {resolved_path.parent}. "
                    "Set create_dirs=True to create it."
                )

            # Determine file mode
            if binary:
                # Decode base64 content
                try:
                    raw_content = base64.b64decode(content)
                except Exception as e:
                    return TaskResult.fail(f"Failed to decode base64 content: {e}")

                file_mode = "ab" if mode == "append" else "wb"
                async with aiofiles.open(resolved_path, mode=file_mode) as f:
                    await f.write(raw_content)
                bytes_written = len(raw_content)
            else:
                file_mode = "a" if mode == "append" else "w"
                async with aiofiles.open(resolved_path, mode=file_mode, encoding=encoding) as f:
                    await f.write(content)
                bytes_written = len(content.encode(encoding))

            return TaskResult.ok(
                output={
                    "path": str(resolved_path),
                    "bytes_written": bytes_written,
                    "mode": mode,
                }
            )

        except PathExistsError as e:
            return TaskResult.fail(str(e))
        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error writing file: {e}")

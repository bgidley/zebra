"""File read action for workflow tasks."""

import base64

import aiofiles
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    PathNotFoundError,
    validate_path,
)


class FileReadAction(TaskAction):
    """Read file contents.

    This action reads the contents of a file and stores them in process
    properties for use by subsequent tasks.

    Properties:
        path: File path to read (supports {{var}} templates)
        encoding: Text encoding (default: "utf-8")
        binary: If True, read as binary and return base64-encoded content
        output_key: Where to store the content (default: "file_content")
        base_directory: Optional sandbox directory for security
        max_file_size: Maximum file size to read in bytes

    Example workflow usage:
        ```yaml
        tasks:
          read_config:
            name: "Read configuration"
            action: file_read
            auto: true
            properties:
              path: "config/settings.json"
              output_key: config_content
        ```

    Output:
        - success: True if file was read successfully
        - output.content: The file content (text or base64)
        - output.path: The resolved file path
        - output.size: File size in bytes
        - output.encoding: Encoding used (or "binary")
    """

    description = "Read file contents and store in process properties."

    inputs = [
        ParameterDef(
            name="path",
            type="string",
            description="File path to read (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="encoding",
            type="string",
            description="Text encoding for reading the file",
            required=False,
            default="utf-8",
        ),
        ParameterDef(
            name="binary",
            type="bool",
            description="If True, read as binary and return base64-encoded content",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the content",
            required=False,
            default="file_content",
        ),
        ParameterDef(
            name="base_directory",
            type="string",
            description="Sandbox directory for security (paths must be within)",
            required=False,
        ),
        ParameterDef(
            name="max_file_size",
            type="int",
            description="Maximum file size to read in bytes",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="content",
            type="string",
            description="The file content (text or base64-encoded)",
            required=True,
        ),
        ParameterDef(
            name="path",
            type="string",
            description="The resolved file path",
            required=True,
        ),
        ParameterDef(
            name="size",
            type="int",
            description="File size in bytes",
            required=True,
        ),
        ParameterDef(
            name="encoding",
            type="string",
            description="Encoding used ('binary' for binary mode)",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Read file contents."""
        # Get and validate path
        path_template = task.properties.get("path")
        if not path_template:
            return TaskResult.fail("No path provided")

        path_str = context.resolve_template(path_template)
        encoding = task.properties.get("encoding", "utf-8")
        binary = task.properties.get("binary", False)
        output_key = task.properties.get("output_key", "file_content")

        # Build config from properties
        config = FileSystemConfig.from_properties(task.properties)

        try:
            # Validate and resolve path
            resolved_path = validate_path(path_str, config, must_exist=True)

            # Check if it's a file
            if not resolved_path.is_file():
                return TaskResult.fail(f"Path is not a file: {resolved_path}")

            # Check file size
            file_size = resolved_path.stat().st_size
            if config.max_file_size and file_size > config.max_file_size:
                return TaskResult.fail(
                    f"File size ({file_size} bytes) exceeds maximum "
                    f"allowed size ({config.max_file_size} bytes)"
                )

            # Read file content
            if binary:
                async with aiofiles.open(resolved_path, mode="rb") as f:
                    raw_content = await f.read()
                content = base64.b64encode(raw_content).decode("ascii")
                used_encoding = "binary"
            else:
                async with aiofiles.open(resolved_path, encoding=encoding) as f:
                    content = await f.read()
                used_encoding = encoding

            # Store in process properties
            context.set_process_property(output_key, content)

            return TaskResult.ok(
                output={
                    "content": content,
                    "path": str(resolved_path),
                    "size": file_size,
                    "encoding": used_encoding,
                }
            )

        except PathNotFoundError as e:
            return TaskResult.fail(str(e))
        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except UnicodeDecodeError as e:
            return TaskResult.fail(
                f"Failed to decode file with encoding '{encoding}': {e}. "
                "Try using binary=true for non-text files."
            )
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error reading file: {e}")

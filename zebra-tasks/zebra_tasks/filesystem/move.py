"""File move action for workflow tasks."""

import asyncio
import shutil

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    PathExistsError,
    PathNotFoundError,
    validate_path,
)


class FileMoveAction(TaskAction):
    """Move or rename a file or directory.

    This action moves files or directories from source to destination.
    Can be used for renaming when source and destination are in the
    same directory.

    Properties:
        source: Source path (supports {{var}} templates)
        destination: Destination path (supports {{var}} templates)
        overwrite: Allow overwriting existing files (default: False)
        create_dirs: Create parent directories if missing (default: True)
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          archive_log:
            name: "Move log to archive"
            action: file_move
            auto: true
            properties:
              source: "logs/current.log"
              destination: "archive/{{date}}.log"
              create_dirs: true
        ```

    Output:
        - success: True if move succeeded
        - output.source: The original source path
        - output.destination: The resolved destination path
        - output.type: "file" or "directory"
    """

    description = "Move or rename a file or directory."

    inputs = [
        ParameterDef(
            name="source",
            type="string",
            description="Source path (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="destination",
            type="string",
            description="Destination path (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="overwrite",
            type="bool",
            description="Allow overwriting existing files",
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
            name="base_directory",
            type="string",
            description="Sandbox directory for security (paths must be within)",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="source",
            type="string",
            description="The original source path",
            required=True,
        ),
        ParameterDef(
            name="destination",
            type="string",
            description="The resolved destination path",
            required=True,
        ),
        ParameterDef(
            name="type",
            type="string",
            description="Type of item moved: 'file' or 'directory'",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Move file or directory."""
        source_template = task.properties.get("source")
        dest_template = task.properties.get("destination")

        if not source_template:
            return TaskResult.fail("No source path provided")
        if not dest_template:
            return TaskResult.fail("No destination path provided")

        source_str = context.resolve_template(source_template)
        dest_str = context.resolve_template(dest_template)

        overwrite = task.properties.get("overwrite", False)
        create_dirs = task.properties.get("create_dirs", True)

        config = FileSystemConfig.from_properties(task.properties)

        try:
            # Validate source exists
            source_path = validate_path(source_str, config, must_exist=True)

            # Validate destination
            dest_path = validate_path(dest_str, config, must_exist=False)

            # Determine type
            if source_path.is_file():
                path_type = "file"
            elif source_path.is_dir():
                path_type = "directory"
            else:
                return TaskResult.fail(f"Source is neither file nor directory: {source_path}")

            # Handle destination that is a directory - move into it
            if dest_path.exists() and dest_path.is_dir() and source_path.is_file():
                dest_path = dest_path / source_path.name

            # Check if destination exists
            if dest_path.exists() and not overwrite:
                raise PathExistsError(
                    f"Destination already exists and overwrite=False: {dest_path}"
                )

            # Create parent directories if needed
            if create_dirs:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
            elif not dest_path.parent.exists():
                return TaskResult.fail(
                    f"Parent directory does not exist: {dest_path.parent}. "
                    "Set create_dirs=True to create it."
                )

            # If destination exists and overwrite is True, remove it first
            if dest_path.exists() and overwrite:
                if dest_path.is_dir():
                    await asyncio.to_thread(shutil.rmtree, dest_path)
                else:
                    await asyncio.to_thread(dest_path.unlink)

            # Perform the move
            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))

            return TaskResult.ok(
                output={
                    "source": str(source_path),
                    "destination": str(dest_path),
                    "type": path_type,
                }
            )

        except PathNotFoundError as e:
            return TaskResult.fail(str(e))
        except PathExistsError as e:
            return TaskResult.fail(str(e))
        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error: {e}")

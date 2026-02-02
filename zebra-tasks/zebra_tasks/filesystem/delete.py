"""File delete action for workflow tasks."""

import asyncio
import shutil

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    validate_path,
)


class FileDeleteAction(TaskAction):
    """Delete a file or directory.

    This action deletes files or directories with safety options
    for handling non-existent paths and recursive deletion.

    Properties:
        path: Path to delete (supports {{var}} templates)
        recursive: Delete directories recursively (default: False)
        missing_ok: Don't fail if path doesn't exist (default: True)
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          cleanup_temp:
            name: "Clean up temp files"
            action: file_delete
            auto: true
            properties:
              path: "temp/processing"
              recursive: true
              missing_ok: true
        ```

    Output:
        - success: True if delete succeeded (or path didn't exist with missing_ok)
        - output.path: The resolved path
        - output.deleted: Whether anything was actually deleted
        - output.type: "file" or "directory" (null if didn't exist)
    """

    description = "Delete a file or directory."

    inputs = [
        ParameterDef(
            name="path",
            type="string",
            description="Path to delete (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="recursive",
            type="bool",
            description="Delete directories and their contents recursively",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="missing_ok",
            type="bool",
            description="Don't fail if path doesn't exist",
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
            description="The resolved path",
            required=True,
        ),
        ParameterDef(
            name="deleted",
            type="bool",
            description="Whether anything was actually deleted",
            required=True,
        ),
        ParameterDef(
            name="type",
            type="string",
            description="Type of item deleted: 'file', 'directory', or null if not found",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Delete file or directory."""
        path_template = task.properties.get("path")
        if not path_template:
            return TaskResult.fail("No path provided")

        path_str = context.resolve_template(path_template)

        recursive = task.properties.get("recursive", False)
        missing_ok = task.properties.get("missing_ok", True)

        config = FileSystemConfig.from_properties(task.properties)

        try:
            # Validate path (don't require existence if missing_ok)
            resolved_path = validate_path(path_str, config, must_exist=not missing_ok)

            # Check if path exists
            if not resolved_path.exists():
                if missing_ok:
                    return TaskResult.ok(
                        output={
                            "path": str(resolved_path),
                            "deleted": False,
                            "type": None,
                        }
                    )
                else:
                    return TaskResult.fail(f"Path does not exist: {resolved_path}")

            # Determine type
            if resolved_path.is_file():
                path_type = "file"
                # Delete file
                await asyncio.to_thread(resolved_path.unlink)
            elif resolved_path.is_dir():
                path_type = "directory"
                if not recursive:
                    # Try to remove empty directory
                    try:
                        await asyncio.to_thread(resolved_path.rmdir)
                    except OSError as e:
                        if "not empty" in str(e).lower() or "directory not empty" in str(e).lower():
                            return TaskResult.fail(
                                f"Directory is not empty and recursive=False: {resolved_path}. "
                                "Set recursive=True to delete non-empty directories."
                            )
                        raise
                else:
                    # Recursively delete directory
                    await asyncio.to_thread(shutil.rmtree, resolved_path)
            else:
                # Handle special files (symlinks, etc.)
                path_type = "other"
                await asyncio.to_thread(resolved_path.unlink)

            return TaskResult.ok(
                output={
                    "path": str(resolved_path),
                    "deleted": True,
                    "type": path_type,
                }
            )

        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error: {e}")

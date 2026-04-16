"""File copy action for workflow tasks."""

import asyncio
import shutil
from pathlib import Path

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    PathExistsError,
    PathNotFoundError,
    validate_path,
)


class FileCopyAction(TaskAction):
    """Copy a file or directory.

    This action copies files or directories from source to destination,
    with options for handling existing files and recursive copying.

    Properties:
        source: Source path (supports {{var}} templates)
        destination: Destination path (supports {{var}} templates)
        overwrite: Allow overwriting existing files (default: False)
        recursive: Copy directories recursively (default: True)
        preserve_metadata: Preserve file metadata (default: True)
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          backup_config:
            name: "Backup configuration"
            action: file_copy
            auto: true
            properties:
              source: "config/settings.json"
              destination: "backups/settings.json.bak"
              overwrite: true
        ```

    Output:
        - success: True if copy succeeded
        - output.source: The resolved source path
        - output.destination: The resolved destination path
        - output.type: "file" or "directory"
        - output.files_copied: Number of files copied (for directories)
    """

    description = "Copy a file or directory to a new location."

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
            name="recursive",
            type="bool",
            description="Copy directories recursively",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="preserve_metadata",
            type="bool",
            description="Preserve file metadata (timestamps, permissions)",
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
            description="The resolved source path",
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
            description="Type of item copied: 'file' or 'directory'",
            required=True,
        ),
        ParameterDef(
            name="files_copied",
            type="int",
            description="Number of files copied",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Copy file or directory."""
        source_template = task.properties.get("source")
        dest_template = task.properties.get("destination")

        if not source_template:
            return TaskResult.fail("No source path provided")
        if not dest_template:
            return TaskResult.fail("No destination path provided")

        source_str = context.resolve_template(source_template)
        dest_str = context.resolve_template(dest_template)

        overwrite = task.properties.get("overwrite", False)
        recursive = task.properties.get("recursive", True)
        preserve_metadata = task.properties.get("preserve_metadata", True)

        config = FileSystemConfig.from_properties(task.properties)

        try:
            # Validate source exists
            source_path = validate_path(source_str, config, must_exist=True)

            # Validate destination (don't require it to exist)
            dest_path = validate_path(dest_str, config, must_exist=False)

            # Check if source is file or directory
            if source_path.is_file():
                return await self._copy_file(source_path, dest_path, overwrite, preserve_metadata)
            elif source_path.is_dir():
                if not recursive:
                    return TaskResult.fail(
                        f"Source is a directory but recursive=False: {source_path}"
                    )
                return await self._copy_directory(
                    source_path, dest_path, overwrite, preserve_metadata
                )
            else:
                return TaskResult.fail(f"Source is neither file nor directory: {source_path}")

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

    async def _copy_file(
        self,
        source: Path,
        dest: Path,
        overwrite: bool,
        preserve_metadata: bool,
    ) -> TaskResult:
        """Copy a single file."""
        # Check if destination exists
        if dest.exists() and not overwrite:
            raise PathExistsError(f"Destination already exists and overwrite=False: {dest}")

        # If dest is a directory, copy into it
        if dest.is_dir():
            dest = dest / source.name

        # Create parent directories
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Run copy in thread to avoid blocking
        def do_copy():
            if preserve_metadata:
                shutil.copy2(source, dest)
            else:
                shutil.copy(source, dest)

        await asyncio.to_thread(do_copy)

        return TaskResult.ok(
            output={
                "source": str(source),
                "destination": str(dest),
                "type": "file",
                "files_copied": 1,
            }
        )

    async def _copy_directory(
        self,
        source: Path,
        dest: Path,
        overwrite: bool,
        preserve_metadata: bool,
    ) -> TaskResult:
        """Copy a directory recursively."""
        # Check if destination exists
        if dest.exists():
            if not overwrite:
                raise PathExistsError(f"Destination already exists and overwrite=False: {dest}")
            # Remove existing directory if overwriting
            await asyncio.to_thread(shutil.rmtree, dest)

        # Run copy in thread to avoid blocking
        def do_copy():
            if preserve_metadata:
                return shutil.copytree(source, dest, copy_function=shutil.copy2)
            else:
                return shutil.copytree(source, dest)

        await asyncio.to_thread(do_copy)

        # Count files copied
        files_copied = sum(1 for _ in dest.rglob("*") if _.is_file())

        return TaskResult.ok(
            output={
                "source": str(source),
                "destination": str(dest),
                "type": "directory",
                "files_copied": files_copied,
            }
        )

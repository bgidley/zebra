"""File information actions for workflow tasks."""

import asyncio
import os
import stat
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    format_size,
    validate_path,
)


class FileExistsAction(TaskAction):
    """Check if a file or directory exists.

    This action checks whether a path exists and optionally verifies
    its type (file vs directory).

    Properties:
        path: Path to check (supports {{var}} templates)
        type: Expected type - "any", "file", or "directory" (default: "any")
        output_key: Where to store result (default: "file_exists")
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          check_config:
            name: "Check if config exists"
            action: file_exists
            auto: true
            properties:
              path: "config/settings.json"
              type: file
              output_key: config_exists
        ```

    Output:
        - success: Always True (check itself succeeded)
        - output.exists: Boolean indicating if path exists
        - output.path: The resolved path
        - output.type: "file", "directory", or null if not exists
    """

    description = "Check if a file or directory exists."

    inputs = [
        ParameterDef(
            name="path",
            type="string",
            description="Path to check (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="type",
            type="string",
            description="Expected type: 'any', 'file', or 'directory'",
            required=False,
            default="any",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="file_exists",
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
            name="exists",
            type="bool",
            description="Whether the path exists (and matches expected type)",
            required=True,
        ),
        ParameterDef(
            name="path",
            type="string",
            description="The resolved path",
            required=True,
        ),
        ParameterDef(
            name="type",
            type="string",
            description="Type of item: 'file', 'directory', 'other', or null if not found",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Check if path exists."""
        path_template = task.properties.get("path")
        if not path_template:
            return TaskResult.fail("No path provided")

        path_str = context.resolve_template(path_template)
        expected_type = task.properties.get("type", "any")
        output_key = task.properties.get("output_key", "file_exists")

        if expected_type not in ("any", "file", "directory"):
            return TaskResult.fail(
                f"Invalid type: {expected_type}. Use 'any', 'file', or 'directory'."
            )

        config = FileSystemConfig.from_properties(task.properties)

        try:
            resolved_path = validate_path(path_str, config, must_exist=False)

            exists = resolved_path.exists()
            actual_type = None

            if exists:
                if resolved_path.is_file():
                    actual_type = "file"
                elif resolved_path.is_dir():
                    actual_type = "directory"
                else:
                    actual_type = "other"

            # Check type match if required
            type_matches = True
            if expected_type != "any" and exists:
                type_matches = actual_type == expected_type

            result_exists = exists and type_matches

            # Store in process properties
            context.set_process_property(output_key, result_exists)

            return TaskResult.ok(
                output={
                    "exists": result_exists,
                    "path": str(resolved_path),
                    "type": actual_type,
                }
            )

        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error: {e}")


class FileInfoAction(TaskAction):
    """Get detailed information about a file or directory.

    This action retrieves metadata about a file including size,
    timestamps, and permissions.

    Properties:
        path: Path to inspect (supports {{var}} templates)
        output_key: Where to store result (default: "file_info")
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          get_info:
            name: "Get file information"
            action: file_info
            auto: true
            properties:
              path: "data/input.csv"
              output_key: input_info
        ```

    Output:
        - success: True if path exists and info was retrieved
        - output.path: The resolved path
        - output.name: File/directory name
        - output.type: "file" or "directory"
        - output.size: Size in bytes (files only)
        - output.size_human: Human-readable size
        - output.created: Creation timestamp (ISO format)
        - output.modified: Last modified timestamp (ISO format)
        - output.accessed: Last access timestamp (ISO format)
        - output.permissions: Permission string (e.g., "rwxr-xr-x")
        - output.is_readable: Whether file is readable
        - output.is_writable: Whether file is writable
        - output.is_executable: Whether file is executable
    """

    description = "Get detailed metadata about a file or directory."

    inputs = [
        ParameterDef(
            name="path",
            type="string",
            description="Path to inspect (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="file_info",
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
            name="name",
            type="string",
            description="File or directory name",
            required=True,
        ),
        ParameterDef(
            name="type",
            type="string",
            description="Type: 'file', 'directory', or 'other'",
            required=True,
        ),
        ParameterDef(
            name="size",
            type="int",
            description="Size in bytes",
            required=True,
        ),
        ParameterDef(
            name="size_human",
            type="string",
            description="Human-readable size (e.g., '1.5 KB')",
            required=True,
        ),
        ParameterDef(
            name="created",
            type="string",
            description="Creation timestamp (ISO format)",
            required=True,
        ),
        ParameterDef(
            name="modified",
            type="string",
            description="Last modified timestamp (ISO format)",
            required=True,
        ),
        ParameterDef(
            name="accessed",
            type="string",
            description="Last access timestamp (ISO format)",
            required=True,
        ),
        ParameterDef(
            name="permissions",
            type="string",
            description="Permission string (e.g., 'rwxr-xr-x')",
            required=True,
        ),
        ParameterDef(
            name="is_readable",
            type="bool",
            description="Whether the file is readable",
            required=True,
        ),
        ParameterDef(
            name="is_writable",
            type="bool",
            description="Whether the file is writable",
            required=True,
        ),
        ParameterDef(
            name="is_executable",
            type="bool",
            description="Whether the file is executable",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Get file information."""
        path_template = task.properties.get("path")
        if not path_template:
            return TaskResult.fail("No path provided")

        path_str = context.resolve_template(path_template)
        output_key = task.properties.get("output_key", "file_info")

        config = FileSystemConfig.from_properties(task.properties)

        try:
            resolved_path = validate_path(path_str, config, must_exist=True)

            # Get stat info - run in thread to avoid blocking
            stat_info = await asyncio.to_thread(resolved_path.stat)

            # Determine type
            if resolved_path.is_file():
                path_type = "file"
                size = stat_info.st_size
            elif resolved_path.is_dir():
                path_type = "directory"
                size = 0  # Directories don't have meaningful size
            else:
                path_type = "other"
                size = stat_info.st_size

            # Format timestamps
            created = datetime.fromtimestamp(stat_info.st_ctime, tz=UTC).isoformat()
            modified = datetime.fromtimestamp(stat_info.st_mtime, tz=UTC).isoformat()
            accessed = datetime.fromtimestamp(stat_info.st_atime, tz=UTC).isoformat()

            # Format permissions
            permissions = stat.filemode(stat_info.st_mode)[1:]  # Remove leading type char

            # Check access
            is_readable = os.access(resolved_path, os.R_OK)
            is_writable = os.access(resolved_path, os.W_OK)
            is_executable = os.access(resolved_path, os.X_OK)

            info = {
                "path": str(resolved_path),
                "name": resolved_path.name,
                "type": path_type,
                "size": size,
                "size_human": format_size(size),
                "created": created,
                "modified": modified,
                "accessed": accessed,
                "permissions": permissions,
                "is_readable": is_readable,
                "is_writable": is_writable,
                "is_executable": is_executable,
            }

            # Store in process properties
            context.set_process_property(output_key, info)

            return TaskResult.ok(output=info)

        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except FileNotFoundError:
            return TaskResult.fail(f"Path not found: {path_str}")
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error: {e}")


class DirectoryListAction(TaskAction):
    """List contents of a directory.

    This action lists files and subdirectories within a directory,
    optionally filtering by pattern.

    Properties:
        path: Directory path to list (supports {{var}} templates)
        pattern: Glob pattern to filter results (e.g., "*.txt")
        recursive: List recursively (default: False)
        include_dirs: Include directories in results (default: True)
        include_files: Include files in results (default: True)
        output_key: Where to store result (default: "directory_contents")
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          list_logs:
            name: "List log files"
            action: directory_list
            auto: true
            properties:
              path: "logs"
              pattern: "*.log"
              recursive: true
              output_key: log_files
        ```

    Output:
        - success: True if directory was listed
        - output.path: The resolved directory path
        - output.entries: List of entry objects with name, type, path
        - output.count: Number of entries found
    """

    description = "List contents of a directory with optional filtering."

    inputs = [
        ParameterDef(
            name="path",
            type="string",
            description="Directory path to list (supports {{var}} templates)",
            required=False,
            default=".",
        ),
        ParameterDef(
            name="pattern",
            type="string",
            description="Glob pattern to filter results (e.g., '*.txt')",
            required=False,
            default="*",
        ),
        ParameterDef(
            name="recursive",
            type="bool",
            description="List recursively in subdirectories",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="include_dirs",
            type="bool",
            description="Include directories in results",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="include_files",
            type="bool",
            description="Include files in results",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the file paths",
            required=False,
            default="directory_contents",
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
            description="The resolved directory path",
            required=True,
        ),
        ParameterDef(
            name="entries",
            type="list[dict]",
            description="List of entry objects with name, path, relative_path, and type",
            required=True,
        ),
        ParameterDef(
            name="count",
            type="int",
            description="Number of entries found",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """List directory contents."""
        path_template = task.properties.get("path", ".")
        path_str = context.resolve_template(path_template)

        pattern = task.properties.get("pattern", "*")
        recursive = task.properties.get("recursive", False)
        include_dirs = task.properties.get("include_dirs", True)
        include_files = task.properties.get("include_files", True)
        output_key = task.properties.get("output_key", "directory_contents")

        config = FileSystemConfig.from_properties(task.properties)

        try:
            resolved_path = validate_path(path_str, config, must_exist=True)

            if not resolved_path.is_dir():
                return TaskResult.fail(f"Path is not a directory: {resolved_path}")

            # Run glob in thread to avoid blocking
            if recursive:
                glob_pattern = f"**/{pattern}"
            else:
                glob_pattern = pattern

            def do_glob():
                return list(resolved_path.glob(glob_pattern))

            matches = await asyncio.to_thread(do_glob)

            # Filter and build entries
            entries = []
            for match in matches:
                is_file = match.is_file()
                is_dir = match.is_dir()

                if is_file and not include_files:
                    continue
                if is_dir and not include_dirs:
                    continue

                entry = {
                    "name": match.name,
                    "path": str(match),
                    "relative_path": str(match.relative_to(resolved_path)),
                    "type": "file" if is_file else "directory" if is_dir else "other",
                }
                entries.append(entry)

            # Sort by path for consistent ordering
            entries.sort(key=lambda e: e["path"])

            result = {
                "path": str(resolved_path),
                "entries": entries,
                "count": len(entries),
            }

            # Store in process properties (just the list of paths for convenience)
            context.set_process_property(output_key, [e["path"] for e in entries])

            return TaskResult.ok(output=result)

        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error: {e}")

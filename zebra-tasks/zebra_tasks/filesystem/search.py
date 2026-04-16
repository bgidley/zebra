"""File search action for workflow tasks."""

import asyncio
import re
from pathlib import Path

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    format_size,
    validate_path,
)


class FileSearchAction(TaskAction):
    """Search for files matching patterns.

    This action searches for files and directories matching glob patterns,
    with optional content search and filtering by file attributes.

    Properties:
        pattern: Glob pattern to match (e.g., "*.txt", "**/*.py")
        directory: Base directory for search (default: ".")
        recursive: Search recursively (default: True)
        include_dirs: Include directories in results (default: False)
        include_files: Include files in results (default: True)
        content_pattern: Regex pattern to search file contents (optional)
        min_size: Minimum file size in bytes (optional)
        max_size: Maximum file size in bytes (optional)
        max_results: Maximum number of results (default: 1000)
        output_key: Where to store results (default: "found_files")
        base_directory: Optional sandbox directory for security

    Example workflow usage:
        ```yaml
        tasks:
          find_logs:
            name: "Find error logs"
            action: file_search
            auto: true
            properties:
              pattern: "**/*.log"
              directory: "logs"
              content_pattern: "ERROR|CRITICAL"
              output_key: error_logs
        ```

    Output:
        - success: True if search completed
        - output.matches: List of matching file info objects
        - output.count: Number of matches found
        - output.truncated: Whether results were truncated due to max_results
    """

    description = "Search for files matching glob patterns with optional content filtering."

    inputs = [
        ParameterDef(
            name="pattern",
            type="string",
            description="Glob pattern to match (e.g., '*.txt', '**/*.py')",
            required=True,
        ),
        ParameterDef(
            name="directory",
            type="string",
            description="Base directory for search",
            required=False,
            default=".",
        ),
        ParameterDef(
            name="recursive",
            type="bool",
            description="Search recursively in subdirectories",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="include_dirs",
            type="bool",
            description="Include directories in results",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="include_files",
            type="bool",
            description="Include files in results",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="content_pattern",
            type="string",
            description="Regex pattern to search within file contents",
            required=False,
        ),
        ParameterDef(
            name="min_size",
            type="int",
            description="Minimum file size in bytes",
            required=False,
        ),
        ParameterDef(
            name="max_size",
            type="int",
            description="Maximum file size in bytes",
            required=False,
        ),
        ParameterDef(
            name="max_results",
            type="int",
            description="Maximum number of results to return",
            required=False,
            default=1000,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the file paths",
            required=False,
            default="found_files",
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
            name="matches",
            type="list[dict]",
            description="List of matching file info objects with path, name, type, size",
            required=True,
        ),
        ParameterDef(
            name="count",
            type="int",
            description="Number of matches found",
            required=True,
        ),
        ParameterDef(
            name="truncated",
            type="bool",
            description="Whether results were truncated due to max_results",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Search for files."""
        pattern = task.properties.get("pattern")
        if not pattern:
            return TaskResult.fail("No pattern provided")

        dir_template = task.properties.get("directory", ".")
        dir_str = context.resolve_template(dir_template)

        recursive = task.properties.get("recursive", True)
        include_dirs = task.properties.get("include_dirs", False)
        include_files = task.properties.get("include_files", True)
        content_pattern = task.properties.get("content_pattern")
        min_size = task.properties.get("min_size")
        max_size = task.properties.get("max_size")
        max_results = task.properties.get("max_results", 1000)
        output_key = task.properties.get("output_key", "found_files")

        config = FileSystemConfig.from_properties(task.properties)

        try:
            # Validate base directory
            base_path = validate_path(dir_str, config, must_exist=True)

            if not base_path.is_dir():
                return TaskResult.fail(f"Path is not a directory: {base_path}")

            # Compile content regex if provided
            content_regex = None
            if content_pattern:
                try:
                    content_regex = re.compile(content_pattern)
                except re.error as e:
                    return TaskResult.fail(f"Invalid content pattern regex: {e}")

            # Search for files
            matches = await self._search_files(
                base_path=base_path,
                pattern=pattern,
                recursive=recursive,
                include_dirs=include_dirs,
                include_files=include_files,
                content_regex=content_regex,
                min_size=min_size,
                max_size=max_size,
                max_results=max_results,
            )

            truncated = len(matches) >= max_results

            # Build result list
            results = []
            for match_path in matches:
                try:
                    stat_info = match_path.stat()
                    is_file = match_path.is_file()

                    result = {
                        "path": str(match_path),
                        "relative_path": str(match_path.relative_to(base_path)),
                        "name": match_path.name,
                        "type": "file" if is_file else "directory",
                        "size": stat_info.st_size if is_file else 0,
                        "size_human": format_size(stat_info.st_size) if is_file else "0 B",
                    }
                    results.append(result)
                except (OSError, PermissionError):
                    # Skip files we can't stat
                    continue

            # Store paths in process properties
            context.set_process_property(output_key, [r["path"] for r in results])

            return TaskResult.ok(
                output={
                    "matches": results,
                    "count": len(results),
                    "truncated": truncated,
                }
            )

        except FileSystemError as e:
            return TaskResult.fail(f"Security error: {e}")
        except PermissionError as e:
            return TaskResult.fail(f"Permission denied: {e}")
        except OSError as e:
            return TaskResult.fail(f"I/O error: {e}")

    async def _search_files(
        self,
        base_path: Path,
        pattern: str,
        recursive: bool,
        include_dirs: bool,
        include_files: bool,
        content_regex: re.Pattern | None,
        min_size: int | None,
        max_size: int | None,
        max_results: int,
    ) -> list[Path]:
        """Search for files matching criteria."""

        def do_search() -> list[Path]:
            matches = []

            # Use glob for pattern matching
            if recursive:
                # If pattern doesn't start with **, add it
                if not pattern.startswith("**"):
                    glob_pattern = f"**/{pattern}"
                else:
                    glob_pattern = pattern
            else:
                glob_pattern = pattern

            for path in base_path.glob(glob_pattern):
                if len(matches) >= max_results:
                    break

                try:
                    is_file = path.is_file()
                    is_dir = path.is_dir()

                    # Filter by type
                    if is_file and not include_files:
                        continue
                    if is_dir and not include_dirs:
                        continue

                    # Filter by size (files only)
                    if is_file and (min_size is not None or max_size is not None):
                        size = path.stat().st_size
                        if min_size is not None and size < min_size:
                            continue
                        if max_size is not None and size > max_size:
                            continue

                    # Filter by content (files only)
                    if is_file and content_regex is not None:
                        if not self._file_contains_pattern(path, content_regex):
                            continue

                    matches.append(path)

                except (OSError, PermissionError):
                    # Skip files we can't access
                    continue

            return matches

        return await asyncio.to_thread(do_search)

    def _file_contains_pattern(self, path: Path, regex: re.Pattern) -> bool:
        """Check if file contains content matching the regex."""
        try:
            # Read file in chunks to handle large files
            with open(path, encoding="utf-8", errors="ignore") as f:
                # Read in chunks of 1MB
                chunk_size = 1024 * 1024
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    if regex.search(chunk):
                        return True
            return False
        except (OSError, PermissionError):
            return False

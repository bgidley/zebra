"""Filesystem task actions for the Zebra workflow engine.

This module provides task actions for file I/O operations:
- Reading and writing files
- Copying, moving, and deleting files/directories
- Searching for files with patterns
- Getting file information and existence checks

All actions support sandboxing via base_directory for security.

Example workflow usage:
    ```yaml
    process:
      id: file-processing
      name: Process Files

    tasks:
      find_files:
        name: "Find log files"
        action: file_search
        auto: true
        properties:
          pattern: "**/*.log"
          directory: "{{input_dir}}"
          output_key: log_files

      read_first:
        name: "Read first log"
        action: file_read
        auto: true
        properties:
          path: "{{log_files[0]}}"
          output_key: log_content

      write_report:
        name: "Write analysis"
        action: file_write
        auto: true
        properties:
          path: "{{output_dir}}/report.txt"
          content: "Analyzed: {{log_content}}"
          create_dirs: true
    ```
"""

from zebra_tasks.filesystem.base import (
    FileSystemConfig,
    FileSystemError,
    PathExistsError,
    PathNotFoundError,
    PathSecurityError,
    format_size,
    validate_path,
)
from zebra_tasks.filesystem.copy import FileCopyAction
from zebra_tasks.filesystem.delete import FileDeleteAction
from zebra_tasks.filesystem.info import (
    DirectoryListAction,
    FileExistsAction,
    FileInfoAction,
)
from zebra_tasks.filesystem.move import FileMoveAction
from zebra_tasks.filesystem.read import FileReadAction
from zebra_tasks.filesystem.search import FileSearchAction
from zebra_tasks.filesystem.write import FileWriteAction

__all__ = [
    # Actions
    "FileReadAction",
    "FileWriteAction",
    "FileCopyAction",
    "FileMoveAction",
    "FileDeleteAction",
    "FileSearchAction",
    "FileExistsAction",
    "FileInfoAction",
    "DirectoryListAction",
    # Utilities
    "FileSystemConfig",
    "validate_path",
    "format_size",
    # Exceptions
    "FileSystemError",
    "PathSecurityError",
    "PathNotFoundError",
    "PathExistsError",
]

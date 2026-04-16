"""Base utilities for filesystem operations.

This module provides shared utilities for filesystem task actions including:
- Path validation and security (sandbox enforcement)
- Error handling and custom exceptions
- Configuration for filesystem operations
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class FileSystemError(Exception):
    """Base exception for filesystem operation errors."""

    pass


class PathSecurityError(FileSystemError):
    """Raised when a path operation violates security constraints."""

    pass


class PathNotFoundError(FileSystemError):
    """Raised when a required path does not exist."""

    pass


class PathExistsError(FileSystemError):
    """Raised when a path unexpectedly exists."""

    pass


@dataclass
class FileSystemConfig:
    """Configuration for filesystem security and limits.

    Attributes:
        base_directory: If set, all paths must resolve within this directory.
            This provides sandboxing to prevent access to sensitive system files.
        max_file_size: Maximum file size in bytes for read operations.
            None means no limit.
        allow_absolute: Whether to allow absolute paths.
            If False, paths must be relative to base_directory.
        follow_symlinks: Whether to follow symbolic links.
            Disabling prevents symlink attacks that escape the sandbox.
    """

    base_directory: Path | None = None
    max_file_size: int | None = None
    allow_absolute: bool = False
    follow_symlinks: bool = False

    @classmethod
    def from_properties(cls, properties: dict[str, Any]) -> "FileSystemConfig":
        """Create config from task properties.

        Properties:
            base_directory: Base directory for sandboxing
            max_file_size: Maximum file size in bytes
            allow_absolute: Whether to allow absolute paths
            follow_symlinks: Whether to follow symlinks
        """
        base_dir = properties.get("base_directory")
        return cls(
            base_directory=Path(base_dir) if base_dir else None,
            max_file_size=properties.get("max_file_size"),
            allow_absolute=properties.get("allow_absolute", False),
            follow_symlinks=properties.get("follow_symlinks", False),
        )


def validate_path(
    path: str | Path,
    config: FileSystemConfig | None = None,
    must_exist: bool = False,
    must_not_exist: bool = False,
) -> Path:
    """Validate and resolve a path with security constraints.

    This function ensures paths are safe to use by:
    1. Resolving relative paths and symlinks
    2. Checking for path traversal attacks (../)
    3. Enforcing sandbox boundaries (base_directory)
    4. Optionally verifying existence

    Args:
        path: The path to validate (string or Path object)
        config: Security configuration, or None for permissive defaults
        must_exist: If True, raise PathNotFoundError if path doesn't exist
        must_not_exist: If True, raise PathExistsError if path exists

    Returns:
        Resolved Path object that is safe to use

    Raises:
        PathSecurityError: If path violates security constraints
        PathNotFoundError: If must_exist=True and path doesn't exist
        PathExistsError: If must_not_exist=True and path exists
    """
    if config is None:
        config = FileSystemConfig(allow_absolute=True, follow_symlinks=True)

    path_obj = Path(path)

    # Check absolute path permission
    if path_obj.is_absolute() and not config.allow_absolute:
        raise PathSecurityError(
            f"Absolute paths are not allowed: {path}. "
            "Use relative paths or set allow_absolute=True."
        )

    # Determine base directory
    if config.base_directory is not None:
        base = config.base_directory.resolve()
    else:
        base = Path.cwd()

    # Resolve the path
    if path_obj.is_absolute():
        resolved = path_obj
    else:
        resolved = base / path_obj

    # Resolve symlinks if allowed, otherwise use strict resolution
    if config.follow_symlinks:
        try:
            resolved = resolved.resolve()
        except OSError:
            # Path may not exist yet, resolve what we can
            resolved = Path(os.path.normpath(resolved))
    else:
        # Don't resolve symlinks - use normpath to handle .. and .
        resolved = Path(os.path.normpath(resolved))

    # Security check: ensure path is within base directory
    if config.base_directory is not None:
        try:
            resolved.relative_to(base)
        except ValueError:
            raise PathSecurityError(
                f"Path '{path}' resolves to '{resolved}' which is outside "
                f"the allowed base directory '{base}'"
            )

    # Check for path traversal in the original path string
    path_str = str(path)
    if ".." in path_str:
        # Double-check the resolved path is still within bounds
        normalized = os.path.normpath(path_str)
        if normalized.startswith(".."):
            raise PathSecurityError(
                f"Path traversal detected in '{path}'. Paths cannot escape the base directory."
            )

    # Existence checks
    if must_exist and not resolved.exists():
        raise PathNotFoundError(f"Path does not exist: {resolved}")

    if must_not_exist and resolved.exists():
        raise PathExistsError(f"Path already exists: {resolved}")

    return resolved


def get_relative_path(path: Path, base: Path | None = None) -> str:
    """Get a path relative to base directory for display/storage.

    Args:
        path: The absolute path
        base: Base directory, or cwd if None

    Returns:
        Relative path string, or absolute path if not relative to base
    """
    if base is None:
        base = Path.cwd()

    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def format_size(size_bytes: int) -> str:
    """Format a file size in human-readable form.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

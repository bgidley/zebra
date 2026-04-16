"""Tests for filesystem task actions."""

import base64
import tempfile
from pathlib import Path

import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.filesystem import (
    DirectoryListAction,
    FileCopyAction,
    FileDeleteAction,
    FileExistsAction,
    FileInfoAction,
    FileMoveAction,
    FileReadAction,
    FileSearchAction,
    FileSystemConfig,
    FileWriteAction,
    PathSecurityError,
    validate_path,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_file(temp_dir):
    """Create a test file with content."""
    file_path = temp_dir / "test.txt"
    file_path.write_text("Hello, World!")
    return file_path


@pytest.fixture
def test_dir_structure(temp_dir):
    """Create a test directory structure."""
    # Create directories
    (temp_dir / "subdir1").mkdir()
    (temp_dir / "subdir2").mkdir()
    (temp_dir / "subdir1" / "nested").mkdir()

    # Create files
    (temp_dir / "file1.txt").write_text("File 1 content")
    (temp_dir / "file2.log").write_text("File 2 content with ERROR")
    (temp_dir / "subdir1" / "file3.txt").write_text("File 3 content")
    (temp_dir / "subdir1" / "nested" / "file4.txt").write_text("File 4 content")
    (temp_dir / "subdir2" / "file5.log").write_text("File 5 content")

    return temp_dir


def make_task(properties: dict) -> TaskInstance:
    """Create a task instance with given properties."""
    return TaskInstance(
        id="test_task",
        process_id="test_process",
        task_definition_id="test_def",
        state=TaskState.RUNNING,
        foe_id="foe_1",
        properties=properties,
    )


# =============================================================================
# Path Validation Tests
# =============================================================================


class TestValidatePath:
    """Tests for the validate_path function."""

    def test_validate_simple_path(self, temp_dir):
        """Test validating a simple relative path."""
        config = FileSystemConfig(base_directory=temp_dir, allow_absolute=False)
        (temp_dir / "test.txt").write_text("content")

        result = validate_path("test.txt", config, must_exist=True)
        assert result == temp_dir / "test.txt"

    def test_validate_path_traversal_blocked(self, temp_dir):
        """Test that path traversal is blocked."""
        config = FileSystemConfig(base_directory=temp_dir, allow_absolute=False)

        with pytest.raises(PathSecurityError):
            validate_path("../outside.txt", config)

    def test_validate_absolute_path_blocked(self, temp_dir):
        """Test that absolute paths are blocked when not allowed."""
        config = FileSystemConfig(base_directory=temp_dir, allow_absolute=False)

        with pytest.raises(PathSecurityError):
            validate_path("/etc/passwd", config)

    def test_validate_absolute_path_allowed(self, temp_dir):
        """Test that absolute paths work when allowed."""
        config = FileSystemConfig(base_directory=None, allow_absolute=True)
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        result = validate_path(str(test_file), config, must_exist=True)
        assert result == test_file

    def test_validate_must_exist_fails(self, temp_dir):
        """Test that must_exist raises for non-existent paths."""
        config = FileSystemConfig(base_directory=temp_dir)

        from zebra_tasks.filesystem.base import PathNotFoundError

        with pytest.raises(PathNotFoundError):
            validate_path("nonexistent.txt", config, must_exist=True)


# =============================================================================
# FileReadAction Tests
# =============================================================================


class TestFileReadAction:
    """Tests for FileReadAction."""

    async def test_read_text_file(self, test_file, mock_context):
        """Test reading a text file."""
        action = FileReadAction()
        task = make_task(
            {
                "path": str(test_file),
                "output_key": "content",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["content"] == "Hello, World!"
        assert result.output["size"] == 13
        assert mock_context.process.properties["content"] == "Hello, World!"

    async def test_read_binary_file(self, temp_dir, mock_context):
        """Test reading a binary file as base64."""
        binary_file = temp_dir / "binary.bin"
        binary_data = bytes([0, 1, 2, 255, 254, 253])
        binary_file.write_bytes(binary_data)

        action = FileReadAction()
        task = make_task(
            {
                "path": str(binary_file),
                "binary": True,
                "output_key": "binary_content",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        decoded = base64.b64decode(result.output["content"])
        assert decoded == binary_data

    async def test_read_nonexistent_file(self, temp_dir, mock_context):
        """Test reading a non-existent file fails."""
        action = FileReadAction()
        task = make_task(
            {
                "path": str(temp_dir / "nonexistent.txt"),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert not result.success
        assert "not found" in result.error.lower() or "does not exist" in result.error.lower()

    async def test_read_with_encoding(self, temp_dir, mock_context):
        """Test reading a file with specific encoding."""
        utf16_file = temp_dir / "utf16.txt"
        utf16_file.write_text("Unicode: \u4e2d\u6587", encoding="utf-16")

        action = FileReadAction()
        task = make_task(
            {
                "path": str(utf16_file),
                "encoding": "utf-16",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert "Unicode:" in result.output["content"]

    async def test_read_no_path_fails(self, mock_context):
        """Test that reading without a path fails."""
        action = FileReadAction()
        task = make_task({})

        result = await action.run(task, mock_context)

        assert not result.success
        assert "no path" in result.error.lower()


# =============================================================================
# FileWriteAction Tests
# =============================================================================


class TestFileWriteAction:
    """Tests for FileWriteAction."""

    async def test_write_text_file(self, temp_dir, mock_context):
        """Test writing a text file."""
        output_file = temp_dir / "output.txt"

        action = FileWriteAction()
        task = make_task(
            {
                "path": str(output_file),
                "content": "Hello, Test!",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert output_file.read_text() == "Hello, Test!"
        assert result.output["bytes_written"] == len(b"Hello, Test!")

    async def test_write_with_append(self, test_file, mock_context):
        """Test appending to a file."""
        action = FileWriteAction()
        task = make_task(
            {
                "path": str(test_file),
                "content": " Appended!",
                "mode": "append",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert test_file.read_text() == "Hello, World! Appended!"

    async def test_write_creates_directories(self, temp_dir, mock_context):
        """Test that directories are created when needed."""
        output_file = temp_dir / "new" / "nested" / "file.txt"

        action = FileWriteAction()
        task = make_task(
            {
                "path": str(output_file),
                "content": "Created!",
                "create_dirs": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert output_file.exists()
        assert output_file.read_text() == "Created!"

    async def test_write_overwrite_false(self, test_file, mock_context):
        """Test that overwrite=False prevents overwriting."""
        action = FileWriteAction()
        task = make_task(
            {
                "path": str(test_file),
                "content": "New content",
                "overwrite": False,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert not result.success
        assert "already exists" in result.error.lower()
        # Original content unchanged
        assert test_file.read_text() == "Hello, World!"

    async def test_write_binary_content(self, temp_dir, mock_context):
        """Test writing binary (base64-encoded) content."""
        output_file = temp_dir / "binary.bin"
        binary_data = bytes([0, 1, 2, 255, 254, 253])
        encoded = base64.b64encode(binary_data).decode("ascii")

        action = FileWriteAction()
        task = make_task(
            {
                "path": str(output_file),
                "content": encoded,
                "binary": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert output_file.read_bytes() == binary_data


# =============================================================================
# FileCopyAction Tests
# =============================================================================


class TestFileCopyAction:
    """Tests for FileCopyAction."""

    async def test_copy_file(self, test_file, temp_dir, mock_context):
        """Test copying a file."""
        dest = temp_dir / "copy.txt"

        action = FileCopyAction()
        task = make_task(
            {
                "source": str(test_file),
                "destination": str(dest),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert dest.exists()
        assert dest.read_text() == "Hello, World!"
        assert test_file.exists()  # Original still exists

    async def test_copy_directory(self, test_dir_structure, temp_dir, mock_context):
        """Test copying a directory recursively."""
        source = test_dir_structure / "subdir1"
        dest = temp_dir / "subdir1_copy"

        action = FileCopyAction()
        task = make_task(
            {
                "source": str(source),
                "destination": str(dest),
                "recursive": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert dest.exists()
        assert (dest / "file3.txt").exists()
        assert (dest / "nested" / "file4.txt").exists()

    async def test_copy_overwrite_false(self, test_file, temp_dir, mock_context):
        """Test that overwrite=False prevents overwriting."""
        dest = temp_dir / "existing.txt"
        dest.write_text("Existing content")

        action = FileCopyAction()
        task = make_task(
            {
                "source": str(test_file),
                "destination": str(dest),
                "overwrite": False,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert not result.success
        assert "already exists" in result.error.lower()


# =============================================================================
# FileMoveAction Tests
# =============================================================================


class TestFileMoveAction:
    """Tests for FileMoveAction."""

    async def test_move_file(self, test_file, temp_dir, mock_context):
        """Test moving a file."""
        dest = temp_dir / "moved.txt"

        action = FileMoveAction()
        task = make_task(
            {
                "source": str(test_file),
                "destination": str(dest),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert dest.exists()
        assert dest.read_text() == "Hello, World!"
        assert not test_file.exists()  # Original should be gone

    async def test_rename_file(self, test_file, mock_context):
        """Test renaming a file (move within same directory)."""
        dest = test_file.parent / "renamed.txt"

        action = FileMoveAction()
        task = make_task(
            {
                "source": str(test_file),
                "destination": str(dest),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert dest.exists()
        assert not test_file.exists()

    async def test_move_creates_directories(self, test_file, temp_dir, mock_context):
        """Test that directories are created when needed."""
        dest = temp_dir / "new" / "nested" / "moved.txt"

        action = FileMoveAction()
        task = make_task(
            {
                "source": str(test_file),
                "destination": str(dest),
                "create_dirs": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert dest.exists()


# =============================================================================
# FileDeleteAction Tests
# =============================================================================


class TestFileDeleteAction:
    """Tests for FileDeleteAction."""

    async def test_delete_file(self, test_file, mock_context):
        """Test deleting a file."""
        action = FileDeleteAction()
        task = make_task(
            {
                "path": str(test_file),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["deleted"]
        assert not test_file.exists()

    async def test_delete_directory_recursive(self, test_dir_structure, mock_context):
        """Test deleting a directory recursively."""
        dir_to_delete = test_dir_structure / "subdir1"

        action = FileDeleteAction()
        task = make_task(
            {
                "path": str(dir_to_delete),
                "recursive": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["deleted"]
        assert not dir_to_delete.exists()

    async def test_delete_nonempty_dir_fails_without_recursive(
        self, test_dir_structure, mock_context
    ):
        """Test that deleting non-empty dir fails without recursive."""
        dir_to_delete = test_dir_structure / "subdir1"

        action = FileDeleteAction()
        task = make_task(
            {
                "path": str(dir_to_delete),
                "recursive": False,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert not result.success
        assert "not empty" in result.error.lower() or "recursive" in result.error.lower()

    async def test_delete_missing_ok(self, temp_dir, mock_context):
        """Test that missing_ok allows deleting non-existent files."""
        action = FileDeleteAction()
        task = make_task(
            {
                "path": str(temp_dir / "nonexistent.txt"),
                "missing_ok": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert not result.output["deleted"]

    async def test_delete_missing_fails(self, temp_dir, mock_context):
        """Test that missing_ok=False fails for non-existent files."""
        action = FileDeleteAction()
        task = make_task(
            {
                "path": str(temp_dir / "nonexistent.txt"),
                "missing_ok": False,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert not result.success


# =============================================================================
# FileSearchAction Tests
# =============================================================================


class TestFileSearchAction:
    """Tests for FileSearchAction."""

    async def test_search_by_extension(self, test_dir_structure, mock_context):
        """Test searching files by extension."""
        action = FileSearchAction()
        task = make_task(
            {
                "pattern": "*.txt",
                "directory": str(test_dir_structure),
                "recursive": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["count"] == 3  # file1.txt, file3.txt, file4.txt
        paths = [m["name"] for m in result.output["matches"]]
        assert "file1.txt" in paths
        assert "file3.txt" in paths
        assert "file4.txt" in paths

    async def test_search_with_content_pattern(self, test_dir_structure, mock_context):
        """Test searching files by content."""
        action = FileSearchAction()
        task = make_task(
            {
                "pattern": "*.log",
                "directory": str(test_dir_structure),
                "content_pattern": "ERROR",
                "recursive": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["count"] == 1
        assert "file2.log" in result.output["matches"][0]["name"]

    async def test_search_non_recursive(self, test_dir_structure, mock_context):
        """Test non-recursive search."""
        action = FileSearchAction()
        task = make_task(
            {
                "pattern": "*.txt",
                "directory": str(test_dir_structure),
                "recursive": False,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["count"] == 1  # Only file1.txt in root
        assert "file1.txt" in result.output["matches"][0]["name"]

    async def test_search_include_dirs(self, test_dir_structure, mock_context):
        """Test searching including directories."""
        action = FileSearchAction()
        task = make_task(
            {
                "pattern": "subdir*",
                "directory": str(test_dir_structure),
                "include_dirs": True,
                "include_files": False,
                "recursive": False,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["count"] == 2  # subdir1, subdir2


# =============================================================================
# FileExistsAction Tests
# =============================================================================


class TestFileExistsAction:
    """Tests for FileExistsAction."""

    async def test_file_exists(self, test_file, mock_context):
        """Test checking that a file exists."""
        action = FileExistsAction()
        task = make_task(
            {
                "path": str(test_file),
                "type": "file",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["exists"]
        assert result.output["type"] == "file"

    async def test_file_not_exists(self, temp_dir, mock_context):
        """Test checking that a file doesn't exist."""
        action = FileExistsAction()
        task = make_task(
            {
                "path": str(temp_dir / "nonexistent.txt"),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success  # The check succeeded
        assert not result.output["exists"]

    async def test_directory_exists(self, temp_dir, mock_context):
        """Test checking that a directory exists."""
        action = FileExistsAction()
        task = make_task(
            {
                "path": str(temp_dir),
                "type": "directory",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["exists"]
        assert result.output["type"] == "directory"

    async def test_type_mismatch(self, test_file, mock_context):
        """Test that type mismatch returns exists=False."""
        action = FileExistsAction()
        task = make_task(
            {
                "path": str(test_file),
                "type": "directory",  # But it's a file
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert not result.output["exists"]


# =============================================================================
# FileInfoAction Tests
# =============================================================================


class TestFileInfoAction:
    """Tests for FileInfoAction."""

    async def test_file_info(self, test_file, mock_context):
        """Test getting file information."""
        action = FileInfoAction()
        task = make_task(
            {
                "path": str(test_file),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["type"] == "file"
        assert result.output["name"] == "test.txt"
        assert result.output["size"] == 13
        assert "modified" in result.output
        assert "permissions" in result.output
        assert result.output["is_readable"]

    async def test_directory_info(self, temp_dir, mock_context):
        """Test getting directory information."""
        action = FileInfoAction()
        task = make_task(
            {
                "path": str(temp_dir),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["type"] == "directory"


# =============================================================================
# DirectoryListAction Tests
# =============================================================================


class TestDirectoryListAction:
    """Tests for DirectoryListAction."""

    async def test_list_directory(self, test_dir_structure, mock_context):
        """Test listing directory contents."""
        action = DirectoryListAction()
        task = make_task(
            {
                "path": str(test_dir_structure),
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        # Should include files and directories in root
        names = [e["name"] for e in result.output["entries"]]
        assert "file1.txt" in names
        assert "file2.log" in names
        assert "subdir1" in names
        assert "subdir2" in names

    async def test_list_with_pattern(self, test_dir_structure, mock_context):
        """Test listing with a pattern filter."""
        action = DirectoryListAction()
        task = make_task(
            {
                "path": str(test_dir_structure),
                "pattern": "*.txt",
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        names = [e["name"] for e in result.output["entries"]]
        assert "file1.txt" in names
        assert "file2.log" not in names

    async def test_list_recursive(self, test_dir_structure, mock_context):
        """Test recursive directory listing."""
        action = DirectoryListAction()
        task = make_task(
            {
                "path": str(test_dir_structure),
                "pattern": "*.txt",
                "recursive": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        assert result.output["count"] == 3  # All .txt files

    async def test_list_files_only(self, test_dir_structure, mock_context):
        """Test listing files only (no directories)."""
        action = DirectoryListAction()
        task = make_task(
            {
                "path": str(test_dir_structure),
                "include_dirs": False,
                "include_files": True,
                "allow_absolute": True,
            }
        )

        result = await action.run(task, mock_context)

        assert result.success
        types = [e["type"] for e in result.output["entries"]]
        assert all(t == "file" for t in types)


# =============================================================================
# Integration Tests
# =============================================================================


class TestFilesystemIntegration:
    """Integration tests combining multiple filesystem operations."""

    async def test_read_write_cycle(self, temp_dir, mock_context):
        """Test writing and reading back a file."""
        file_path = temp_dir / "roundtrip.txt"
        content = "Test content for roundtrip"

        # Write
        write_action = FileWriteAction()
        write_task = make_task(
            {
                "path": str(file_path),
                "content": content,
                "allow_absolute": True,
            }
        )
        write_result = await write_action.run(write_task, mock_context)
        assert write_result.success

        # Read
        read_action = FileReadAction()
        read_task = make_task(
            {
                "path": str(file_path),
                "allow_absolute": True,
            }
        )
        read_result = await read_action.run(read_task, mock_context)
        assert read_result.success
        assert read_result.output["content"] == content

    async def test_search_and_process(self, test_dir_structure, mock_context):
        """Test searching for files and processing them."""
        # Search for log files
        search_action = FileSearchAction()
        search_task = make_task(
            {
                "pattern": "*.log",
                "directory": str(test_dir_structure),
                "recursive": True,
                "output_key": "log_files",
                "allow_absolute": True,
            }
        )
        search_result = await search_action.run(search_task, mock_context)
        assert search_result.success
        assert search_result.output["count"] == 2

        # Verify files are stored in process properties
        log_files = mock_context.process.properties["log_files"]
        assert len(log_files) == 2

    async def test_copy_modify_delete(self, test_file, temp_dir, mock_context):
        """Test copying, modifying, and deleting a file."""
        copy_path = temp_dir / "copy.txt"

        # Copy
        copy_action = FileCopyAction()
        copy_task = make_task(
            {
                "source": str(test_file),
                "destination": str(copy_path),
                "allow_absolute": True,
            }
        )
        await copy_action.run(copy_task, mock_context)

        # Append to copy
        write_action = FileWriteAction()
        write_task = make_task(
            {
                "path": str(copy_path),
                "content": " Modified!",
                "mode": "append",
                "allow_absolute": True,
            }
        )
        await write_action.run(write_task, mock_context)

        # Verify content
        read_action = FileReadAction()
        read_task = make_task(
            {
                "path": str(copy_path),
                "allow_absolute": True,
            }
        )
        read_result = await read_action.run(read_task, mock_context)
        assert read_result.output["content"] == "Hello, World! Modified!"

        # Delete
        delete_action = FileDeleteAction()
        delete_task = make_task(
            {
                "path": str(copy_path),
                "allow_absolute": True,
            }
        )
        delete_result = await delete_action.run(delete_task, mock_context)
        assert delete_result.success
        assert not copy_path.exists()

        # Original still exists
        assert test_file.exists()

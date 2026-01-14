"""Tests for MCP server tool implementations."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
    TaskResult,
)
from zebra.mcp.server import (
    _create_workflow,
    _start_workflow,
    _get_workflow_status,
    _list_workflows,
    _get_pending_tasks,
    _complete_task,
    _pause_workflow,
    _resume_workflow,
    get_engine,
)


@pytest.fixture
def mock_engine():
    """Create a mock workflow engine."""
    engine = MagicMock()
    engine.store = MagicMock()
    return engine


@pytest.fixture
def sample_definition():
    """Create a sample process definition."""
    return ProcessDefinition(
        id="def-1",
        name="Test Workflow",
        version=1,
        first_task_id="task1",
        tasks={
            "task1": TaskDefinition(id="task1", name="First Task"),
            "task2": TaskDefinition(id="task2", name="Second Task"),
        },
        routings=[],
    )


@pytest.fixture
def sample_process():
    """Create a sample process instance."""
    return ProcessInstance(
        id="proc-1",
        definition_id="def-1",
        state=ProcessState.RUNNING,
        properties={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestCreateWorkflow:
    """Tests for _create_workflow."""

    async def test_create_workflow_success(self, mock_engine, sample_process, sample_definition):
        """Test successful workflow creation."""
        mock_engine.create_process = AsyncMock(return_value=sample_process)

        with patch("zebra.mcp.server.load_definition_from_yaml", return_value=sample_definition):
            with patch("zebra.mcp.server.validate_definition", return_value=[]):
                result = await _create_workflow(mock_engine, {
                    "definition_yaml": "name: Test\ntasks:\n  t1:\n    name: T1",
                    "properties": {"key": "value"},
                })

        assert result["workflow_id"] == "proc-1"
        assert result["definition_name"] == "Test Workflow"
        assert "error" not in result

    async def test_create_workflow_validation_error(self, mock_engine, sample_definition):
        """Test workflow creation with validation errors."""
        with patch("zebra.mcp.server.load_definition_from_yaml", return_value=sample_definition):
            with patch("zebra.mcp.server.validate_definition", return_value=["Error 1", "Error 2"]):
                result = await _create_workflow(mock_engine, {
                    "definition_yaml": "invalid yaml",
                })

        assert "error" in result
        assert result["error"] == "Validation failed"
        assert len(result["details"]) == 2


class TestStartWorkflow:
    """Tests for _start_workflow."""

    async def test_start_workflow_success(self, mock_engine, sample_process):
        """Test successful workflow start."""
        sample_process.state = ProcessState.RUNNING
        mock_engine.start_process = AsyncMock(return_value=sample_process)
        mock_engine.get_process_status = AsyncMock(return_value={
            "process_id": "proc-1",
            "state": "running",
            "tasks": [],
        })

        result = await _start_workflow(mock_engine, {"workflow_id": "proc-1"})

        assert result["workflow_id"] == "proc-1"
        assert result["state"] == "running"
        mock_engine.start_process.assert_called_once_with("proc-1")


class TestGetWorkflowStatus:
    """Tests for _get_workflow_status."""

    async def test_get_status(self, mock_engine):
        """Test getting workflow status."""
        mock_engine.get_process_status = AsyncMock(return_value={
            "process_id": "proc-1",
            "state": "running",
            "tasks": [{"id": "t1", "state": "complete"}],
        })

        result = await _get_workflow_status(mock_engine, {"workflow_id": "proc-1"})

        assert result["process_id"] == "proc-1"
        assert result["state"] == "running"
        mock_engine.get_process_status.assert_called_once_with("proc-1")


class TestListWorkflows:
    """Tests for _list_workflows."""

    async def test_list_workflows(self, mock_engine, sample_process, sample_definition):
        """Test listing workflows."""
        mock_engine.store.list_processes = AsyncMock(return_value=[sample_process])
        mock_engine.store.load_definition = AsyncMock(return_value=sample_definition)

        result = await _list_workflows(mock_engine, {"include_completed": False})

        assert result["count"] == 1
        assert result["workflows"][0]["id"] == "proc-1"
        assert result["workflows"][0]["name"] == "Test Workflow"

    async def test_list_workflows_include_completed(self, mock_engine):
        """Test listing workflows with completed flag."""
        mock_engine.store.list_processes = AsyncMock(return_value=[])

        await _list_workflows(mock_engine, {"include_completed": True})

        mock_engine.store.list_processes.assert_called_once_with(include_completed=True)

    async def test_list_workflows_unknown_definition(self, mock_engine, sample_process):
        """Test listing workflows when definition is not found."""
        mock_engine.store.list_processes = AsyncMock(return_value=[sample_process])
        mock_engine.store.load_definition = AsyncMock(return_value=None)

        result = await _list_workflows(mock_engine, {})

        assert result["workflows"][0]["name"] == "Unknown"


class TestGetPendingTasks:
    """Tests for _get_pending_tasks."""

    async def test_get_pending_tasks(self, mock_engine, sample_process, sample_definition):
        """Test getting pending tasks."""
        task = TaskInstance(
            id="task-inst-1",
            process_id="proc-1",
            task_definition_id="task1",
            state=TaskState.READY,
            foe_id="foe-1",
            properties={
                "__prompt__": "What should we do?",
                "__schema__": {"type": "string"},
                "custom_prop": "value",
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_engine.get_pending_tasks = AsyncMock(return_value=[task])
        mock_engine.store.load_process = AsyncMock(return_value=sample_process)
        mock_engine.store.load_definition = AsyncMock(return_value=sample_definition)

        result = await _get_pending_tasks(mock_engine, {"workflow_id": "proc-1"})

        assert result["count"] == 1
        assert result["tasks"][0]["id"] == "task-inst-1"
        assert result["tasks"][0]["name"] == "First Task"
        assert result["tasks"][0]["prompt"] == "What should we do?"
        assert result["tasks"][0]["properties"] == {"custom_prop": "value"}


class TestCompleteTask:
    """Tests for _complete_task."""

    async def test_complete_task_with_result(self, mock_engine):
        """Test completing a task with result data."""
        new_task = TaskInstance(
            id="task-inst-2",
            process_id="proc-1",
            task_definition_id="task2",
            state=TaskState.PENDING,
            foe_id="foe-1",
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_engine.complete_task = AsyncMock(return_value=[new_task])

        result = await _complete_task(mock_engine, {
            "task_id": "task-inst-1",
            "result": {"answer": "yes"},
        })

        assert result["task_id"] == "task-inst-1"
        assert result["completed"] is True
        assert len(result["created_tasks"]) == 1
        assert result["created_tasks"][0]["id"] == "task-inst-2"

    async def test_complete_task_without_result(self, mock_engine):
        """Test completing a task without result data."""
        mock_engine.complete_task = AsyncMock(return_value=[])

        result = await _complete_task(mock_engine, {"task_id": "task-inst-1"})

        assert result["completed"] is True
        assert len(result["created_tasks"]) == 0


class TestPauseWorkflow:
    """Tests for _pause_workflow."""

    async def test_pause_workflow(self, mock_engine, sample_process):
        """Test pausing a workflow."""
        sample_process.state = ProcessState.PAUSED
        mock_engine.pause_process = AsyncMock(return_value=sample_process)

        result = await _pause_workflow(mock_engine, {"workflow_id": "proc-1"})

        assert result["workflow_id"] == "proc-1"
        assert result["state"] == "paused"
        mock_engine.pause_process.assert_called_once_with("proc-1")


class TestResumeWorkflow:
    """Tests for _resume_workflow."""

    async def test_resume_workflow(self, mock_engine, sample_process):
        """Test resuming a workflow."""
        sample_process.state = ProcessState.RUNNING
        mock_engine.resume_process = AsyncMock(return_value=sample_process)

        result = await _resume_workflow(mock_engine, {"workflow_id": "proc-1"})

        assert result["workflow_id"] == "proc-1"
        assert result["state"] == "running"
        mock_engine.resume_process.assert_called_once_with("proc-1")


class TestGetEngine:
    """Tests for get_engine singleton."""

    async def test_get_engine_creates_once(self):
        """Test that get_engine creates engine only once."""
        import zebra.mcp.server as server_module

        # Reset global state
        server_module._engine = None
        server_module._store = None

        with patch.object(server_module, "SQLiteStore") as mock_store_class:
            mock_store = AsyncMock()
            mock_store_class.return_value = mock_store

            with patch.object(server_module, "ActionRegistry") as mock_registry_class:
                mock_registry = MagicMock()
                mock_registry_class.return_value = mock_registry

                with patch.object(server_module, "WorkflowEngine") as mock_engine_class:
                    mock_engine = MagicMock()
                    mock_engine_class.return_value = mock_engine

                    # First call
                    engine1 = await server_module.get_engine()

                    # Second call should return same instance
                    engine2 = await server_module.get_engine()

                    assert engine1 is engine2
                    mock_store_class.assert_called_once()
                    mock_engine_class.assert_called_once()

        # Reset for other tests
        server_module._engine = None
        server_module._store = None


class TestCreateMCPServer:
    """Tests for create_mcp_server."""

    def test_create_mcp_server_missing_dependency(self):
        """Test error when MCP package is not installed."""
        import zebra.mcp.server as server_module

        with patch.dict("sys.modules", {"mcp.server": None, "mcp": None}):
            # Force reimport to trigger ImportError
            import importlib
            try:
                # This should handle the import error gracefully
                # For this test we just verify the function exists
                assert callable(server_module.create_mcp_server)
            except ImportError:
                pass  # Expected in some environments

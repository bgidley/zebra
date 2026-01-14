"""Tests for subtask actions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
)

from zebra_tasks.subtasks import (
    SubworkflowAction,
    WaitForSubworkflowAction,
    ParallelSubworkflowsAction,
)


class TestSubworkflowAction:
    """Tests for SubworkflowAction."""

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_with_inline_definition(
        self, mock_context, mock_task, simple_workflow_definition
    ):
        """Test spawning a sub-workflow with inline definition."""
        # Setup
        mock_task.properties = {
            "workflow": {
                "id": "inline_workflow",
                "name": "Inline Workflow",
                "first_task_id": "t1",
                "tasks": {
                    "t1": {"id": "t1", "name": "T1", "action": "test"},
                },
                "routings": [],
            },
            "wait": False,
            "output_key": "sub_process_id",
        }

        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        # Verify
        assert result.success is True
        assert "process_id" in result.output
        assert len(mock_context.engine.created_processes) == 1
        assert len(mock_context.engine.started_processes) == 1

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_inherits_parent_properties(
        self, mock_context, mock_task
    ):
        """Test that sub-workflow inherits special properties from parent."""
        # Setup parent with special properties
        mock_context.process.properties["__llm_provider__"] = "test_provider"
        mock_context.process.properties["__memory__"] = "test_memory"

        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            },
            "wait": False,
        }

        action = SubworkflowAction()
        await action.run(mock_task, mock_context)

        # Verify inheritance
        created = mock_context.engine.created_processes[0]
        assert created.properties.get("__llm_provider__") == "test_provider"
        assert created.properties.get("__memory__") == "test_memory"
        assert created.properties.get("__parent_process_id__") == mock_context.process.id
        assert created.properties.get("__parent_task_id__") == mock_task.id

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_with_custom_properties(
        self, mock_context, mock_task
    ):
        """Test passing custom properties to sub-workflow."""
        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            },
            "properties": {
                "input_data": "test_data",
                "config": {"key": "value"},
            },
            "wait": False,
        }

        action = SubworkflowAction()
        await action.run(mock_task, mock_context)

        created = mock_context.engine.created_processes[0]
        assert created.properties.get("input_data") == "test_data"
        assert created.properties.get("config") == {"key": "value"}

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_wait_for_completion(
        self, mock_context, mock_task, mock_store
    ):
        """Test waiting for sub-workflow completion."""
        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            },
            "wait": True,
            "output_key": "result",
        }

        action = SubworkflowAction()

        # Make the process complete quickly
        async def complete_process():
            await asyncio.sleep(0.05)
            proc = mock_store.processes.get("proc_0")
            if proc:
                proc.state = ProcessState.COMPLETE
                proc.properties["__output__"] = {"data": "completed"}

        asyncio.create_task(complete_process())

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert mock_context.process.properties.get("result")["success"] is True

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_no_definition_fails(self, mock_context, mock_task):
        """Test that missing workflow definition fails gracefully."""
        mock_task.properties = {}

        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No workflow definition" in result.error


class TestWaitForSubworkflowAction:
    """Tests for WaitForSubworkflowAction."""

    @pytest.mark.asyncio
    async def test_wait_for_completed_process(self, mock_context, mock_task, mock_store):
        """Test waiting for an already completed process."""
        # Create a completed process
        completed_process = ProcessInstance(
            id="completed_proc",
            definition_id="test_def",
            state=ProcessState.COMPLETE,
            properties={"__output__": {"result": "success"}},
        )
        mock_store.processes["completed_proc"] = completed_process

        mock_task.properties = {
            "process_id": "completed_proc",
            "output_key": "wait_result",
        }

        action = WaitForSubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert mock_context.process.properties["wait_result"]["success"] is True

    @pytest.mark.asyncio
    async def test_wait_for_failed_process(self, mock_context, mock_task, mock_store):
        """Test waiting for a failed process."""
        failed_process = ProcessInstance(
            id="failed_proc",
            definition_id="test_def",
            state=ProcessState.FAILED,
            properties={"__error__": "Something went wrong"},
        )
        mock_store.processes["failed_proc"] = failed_process

        mock_task.properties = {
            "process_id": "failed_proc",
        }

        action = WaitForSubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Something went wrong" in result.error

    @pytest.mark.asyncio
    async def test_wait_with_template_process_id(self, mock_context, mock_task, mock_store):
        """Test using template variable for process ID."""
        completed_process = ProcessInstance(
            id="proc_123",
            definition_id="test_def",
            state=ProcessState.COMPLETE,
            properties={},
        )
        mock_store.processes["proc_123"] = completed_process
        mock_context.process.properties["spawned_id"] = "proc_123"

        mock_task.properties = {
            "process_id": "{{spawned_id}}",
        }

        action = WaitForSubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_wait_no_process_id_fails(self, mock_context, mock_task):
        """Test that missing process_id fails."""
        mock_task.properties = {}

        action = WaitForSubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No process_id" in result.error


class TestParallelSubworkflowsAction:
    """Tests for ParallelSubworkflowsAction."""

    @pytest.mark.asyncio
    async def test_spawn_multiple_workflows(self, mock_context, mock_task, mock_store):
        """Test spawning multiple workflows in parallel."""
        mock_task.properties = {
            "workflows": [
                {
                    "workflow": {
                        "id": "wf1",
                        "name": "Workflow 1",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "key": "result1",
                },
                {
                    "workflow": {
                        "id": "wf2",
                        "name": "Workflow 2",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "key": "result2",
                },
            ],
            "output_key": "parallel_results",
        }

        # Complete processes quickly
        async def complete_processes():
            await asyncio.sleep(0.05)
            for proc in mock_store.processes.values():
                proc.state = ProcessState.COMPLETE
                proc.properties["__output__"] = {"status": "done"}

        asyncio.create_task(complete_processes())

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert len(mock_context.engine.created_processes) == 2
        assert len(mock_context.engine.started_processes) == 2

        results = mock_context.process.properties["parallel_results"]
        assert "result1" in results
        assert "result2" in results

    @pytest.mark.asyncio
    async def test_parallel_with_custom_properties(self, mock_context, mock_task, mock_store):
        """Test passing different properties to each workflow."""
        mock_context.process.properties["shared_data"] = "shared"

        mock_task.properties = {
            "workflows": [
                {
                    "workflow": {
                        "id": "wf1",
                        "name": "WF1",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "properties": {"input": "data1"},
                    "key": "wf1",
                },
                {
                    "workflow": {
                        "id": "wf2",
                        "name": "WF2",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "properties": {"input": "data2"},
                    "key": "wf2",
                },
            ],
        }

        # Complete immediately
        async def complete():
            await asyncio.sleep(0.02)
            for p in mock_store.processes.values():
                p.state = ProcessState.COMPLETE

        asyncio.create_task(complete())

        action = ParallelSubworkflowsAction()
        await action.run(mock_task, mock_context)

        # Verify each workflow got its own properties
        procs = mock_context.engine.created_processes
        assert procs[0].properties.get("input") == "data1"
        assert procs[1].properties.get("input") == "data2"

    @pytest.mark.asyncio
    async def test_parallel_empty_workflows_fails(self, mock_context, mock_task):
        """Test that empty workflows list fails."""
        mock_task.properties = {"workflows": []}

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No workflows" in result.error

    @pytest.mark.asyncio
    async def test_parallel_fail_fast(self, mock_context, mock_task, mock_store):
        """Test fail_fast option stops on first failure."""
        mock_task.properties = {
            "workflows": [
                {
                    "workflow": {
                        "id": "wf1",
                        "name": "WF1",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "key": "wf1",
                },
                {
                    "workflow": {
                        "id": "wf2",
                        "name": "WF2",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "key": "wf2",
                },
            ],
            "fail_fast": True,
        }

        # First workflow fails
        async def fail_first():
            await asyncio.sleep(0.02)
            procs = list(mock_store.processes.values())
            if procs:
                procs[0].state = ProcessState.FAILED
                procs[0].properties["__error__"] = "First failed"

        asyncio.create_task(fail_first())

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        # Should have partial results due to fail_fast
        assert result.output is not None

    @pytest.mark.asyncio
    async def test_parallel_fail_fast_no_definition(self, mock_context, mock_task):
        """Test fail_fast with missing workflow definition fails immediately."""
        mock_task.properties = {
            "workflows": [
                {"key": "wf1"},  # No workflow definition
            ],
            "fail_fast": True,
        }

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No workflow definition" in result.error

    @pytest.mark.asyncio
    async def test_parallel_skip_no_definition(self, mock_context, mock_task, mock_store):
        """Test skipping workflow with no definition when fail_fast is False."""
        mock_task.properties = {
            "workflows": [
                {"key": "wf1"},  # No workflow definition - will be skipped
                {
                    "workflow": {
                        "id": "wf2",
                        "name": "WF2",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "key": "wf2",
                },
            ],
            "fail_fast": False,
        }

        async def complete_all():
            await asyncio.sleep(0.02)
            for p in mock_store.processes.values():
                p.state = ProcessState.COMPLETE

        asyncio.create_task(complete_all())

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        # Should still succeed (skipping missing definition)
        assert result.success is True
        assert len(mock_context.engine.created_processes) == 1


class TestSubworkflowTimeoutAndEdgeCases:
    """Additional tests for timeout and edge cases."""

    @pytest.mark.asyncio
    async def test_subworkflow_timeout(self, mock_context, mock_task, mock_store):
        """Test subworkflow timeout handling."""
        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            },
            "wait": True,
            "timeout": 0.1,  # 100ms timeout
        }

        # Don't complete the process - let it timeout
        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_subworkflow_process_not_found(self, mock_context, mock_task, mock_store):
        """Test subworkflow with process disappearing."""
        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            },
            "wait": True,
        }

        # Delete the process after creation
        async def delete_process():
            await asyncio.sleep(0.02)
            mock_store.processes.clear()

        asyncio.create_task(delete_process())

        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Process not found" in result.error

    @pytest.mark.asyncio
    async def test_subworkflow_with_yaml_string(self, mock_context, mock_task):
        """Test loading workflow from YAML string."""
        yaml_workflow = """
name: YAML Workflow
first_task_id: t1
tasks:
  t1:
    name: Task 1
"""
        mock_task.properties = {
            "workflow": yaml_workflow,
            "wait": False,
        }

        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert len(mock_context.engine.created_processes) == 1

    @pytest.mark.asyncio
    async def test_subworkflow_with_definition_id(self, mock_context, mock_task, mock_store):
        """Test loading workflow from definition ID in store."""
        # Add definition to store
        mock_store.definitions["stored_def"] = ProcessDefinition(
            id="stored_def",
            name="Stored Workflow",
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[],
        )

        mock_task.properties = {
            "workflow": "stored_def",  # Definition ID
            "wait": False,
        }

        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert len(mock_context.engine.created_processes) == 1

    @pytest.mark.asyncio
    async def test_subworkflow_with_process_definition_object(self, mock_context, mock_task):
        """Test passing ProcessDefinition object directly."""
        from zebra.core.models import ProcessDefinition, TaskDefinition

        mock_task.properties = {
            "workflow": ProcessDefinition(
                id="direct_def",
                name="Direct Workflow",
                first_task_id="t1",
                tasks={"t1": TaskDefinition(id="t1", name="T1")},
                routings=[],
            ),
            "wait": False,
        }

        action = SubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_wait_timeout(self, mock_context, mock_task, mock_store):
        """Test WaitForSubworkflowAction with timeout."""
        # Create a running process that won't complete
        running_process = ProcessInstance(
            id="running_proc",
            definition_id="test_def",
            state=ProcessState.RUNNING,
        )
        mock_store.processes["running_proc"] = running_process

        mock_task.properties = {
            "process_id": "running_proc",
            "timeout": 0.1,  # 100ms timeout
        }

        action = WaitForSubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_wait_process_not_found(self, mock_context, mock_task, mock_store):
        """Test WaitForSubworkflowAction with non-existent process."""
        mock_task.properties = {
            "process_id": "nonexistent_proc",
        }

        action = WaitForSubworkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Process not found" in result.error

    @pytest.mark.asyncio
    async def test_parallel_with_timeout(self, mock_context, mock_task, mock_store):
        """Test ParallelSubworkflowsAction with timeout."""
        mock_task.properties = {
            "workflows": [
                {
                    "workflow": {
                        "id": "wf1",
                        "name": "WF1",
                        "first_task_id": "t1",
                        "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                        "routings": [],
                    },
                    "key": "wf1",
                },
            ],
            "timeout": 0.1,
        }

        # Don't complete - let it timeout
        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        # Should complete with partial_failure or failure route
        assert result.output is not None
        assert result.next_route in ("partial_failure", "failure")

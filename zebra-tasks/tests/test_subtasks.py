"""Tests for subtask actions."""

import pytest
from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
)

from zebra_tasks.subtasks import (
    ParallelSubworkflowsAction,
    SubworkflowAction,
    WaitForSubworkflowAction,
)


def subflow_entry(
    process_id: str,
    success: bool = True,
    properties: dict | None = None,
    error: str | None = None,
) -> dict:
    """A ``context.subflow_results`` entry as the engine builds it on resume (#146)."""
    return {
        "process_id": process_id,
        "workflow": "Test",
        "success": success,
        "output": None,
        "error": error,
        "properties": properties or {},
    }


def child_of(mock_context, process_id: str, state: ProcessState, **properties) -> ProcessInstance:
    """A process linked as a sub-workflow of the context's process."""
    return ProcessInstance(
        id=process_id,
        definition_id="test_def",
        state=state,
        properties=properties,
        parent_process_id=mock_context.process.id,
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
    async def test_spawn_subworkflow_inherits_parent_properties(self, mock_context, mock_task):
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
    async def test_spawn_subworkflow_with_custom_properties(self, mock_context, mock_task):
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
    async def test_spawn_subworkflow_wait_suspends_on_child(self, mock_context, mock_task):
        """Waiting starts the linked child and suspends on it instead of polling (#181)."""
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

        result = await SubworkflowAction().run(mock_task, mock_context)

        assert result.suspend_children == ["proc_0"]
        assert mock_context.engine.started_processes == ["proc_0"]
        child = mock_context.store.processes["proc_0"]
        assert child.parent_process_id == mock_context.process.id
        assert child.parent_task_id == mock_task.id
        assert "result" not in mock_context.process.properties

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_resume_with_completed_child(self, mock_context, mock_task):
        """On resume the result is built from the child's properties."""
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
        mock_context.subflow_results = [
            subflow_entry("proc_0", properties={"__output__": {"data": "completed"}})
        ]

        result = await SubworkflowAction().run(mock_task, mock_context)

        assert result.success is True
        expected = {
            "success": True,
            "process_id": "proc_0",
            "properties": {"__output__": {"data": "completed"}},
            "output": {"data": "completed"},
        }
        assert result.output == expected
        assert mock_context.process.properties["result"] == expected
        assert mock_context.engine.created_processes == []

    @pytest.mark.asyncio
    async def test_spawn_subworkflow_resume_with_failed_child(self, mock_context, mock_task):
        """A failed child fails the task with the child's error."""
        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            }
        }
        mock_context.subflow_results = [
            subflow_entry("proc_0", success=False, error="Something went wrong")
        ]

        result = await SubworkflowAction().run(mock_task, mock_context)

        assert result.success is False
        assert result.error == "Something went wrong"
        assert mock_context.process.properties["subworkflow_result"] == {
            "success": False,
            "error": "Something went wrong",
            "process_id": "proc_0",
        }

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
    async def test_wait_suspends_on_child(self, mock_context, mock_task, mock_store):
        """Waiting on a sub-workflow suspends on it instead of polling (#181)."""
        mock_store.processes["running_proc"] = child_of(
            mock_context, "running_proc", ProcessState.RUNNING
        )
        mock_task.properties = {"process_id": "running_proc", "output_key": "wait_result"}

        result = await WaitForSubworkflowAction().run(mock_task, mock_context)

        assert result.suspend_children == ["running_proc"]
        assert "wait_result" not in mock_context.process.properties

    @pytest.mark.asyncio
    async def test_wait_for_completed_process(self, mock_context, mock_task):
        """On resume a completed child's output is returned."""
        mock_task.properties = {"process_id": "completed_proc", "output_key": "wait_result"}
        mock_context.subflow_results = [
            subflow_entry("completed_proc", properties={"__output__": {"result": "success"}})
        ]

        result = await WaitForSubworkflowAction().run(mock_task, mock_context)

        assert result.success is True
        assert mock_context.process.properties["wait_result"]["success"] is True
        assert mock_context.process.properties["wait_result"]["output"] == {"result": "success"}

    @pytest.mark.asyncio
    async def test_wait_for_failed_process(self, mock_context, mock_task):
        """On resume a failed child fails the task."""
        mock_task.properties = {"process_id": "failed_proc"}
        mock_context.subflow_results = [
            subflow_entry("failed_proc", success=False, error="Something went wrong")
        ]

        result = await WaitForSubworkflowAction().run(mock_task, mock_context)

        assert result.success is False
        assert "Something went wrong" in result.error

    @pytest.mark.asyncio
    async def test_wait_with_template_process_id(self, mock_context, mock_task, mock_store):
        """Test using template variable for process ID."""
        mock_store.processes["proc_123"] = child_of(mock_context, "proc_123", ProcessState.COMPLETE)
        mock_context.process.properties["spawned_id"] = "proc_123"

        mock_task.properties = {
            "process_id": "{{spawned_id}}",
        }

        result = await WaitForSubworkflowAction().run(mock_task, mock_context)

        assert result.suspend_children == ["proc_123"]

    @pytest.mark.asyncio
    async def test_wait_rejects_process_that_is_not_a_child(
        self, mock_context, mock_task, mock_store
    ):
        """Only a child's end resumes the task, so other processes can't be waited on."""
        mock_store.processes["other_proc"] = ProcessInstance(
            id="other_proc",
            definition_id="test_def",
            state=ProcessState.RUNNING,
            parent_process_id="someone_else",
        )
        mock_task.properties = {"process_id": "other_proc"}

        result = await WaitForSubworkflowAction().run(mock_task, mock_context)

        assert result.success is False
        assert result.suspend_children is None
        assert "not a sub-workflow" in result.error

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
        """All workflows start, and the task suspends on them with their keys kept."""
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

        result = await ParallelSubworkflowsAction().run(mock_task, mock_context)

        assert result.suspend_children == ["proc_0", "proc_1"]
        assert len(mock_context.engine.created_processes) == 2
        assert len(mock_context.engine.started_processes) == 2
        assert mock_task.properties["__subflow_keys__"] == {
            "proc_0": "result1",
            "proc_1": "result2",
        }

    @pytest.mark.asyncio
    async def test_parallel_resume_all_succeed(self, mock_context, mock_task):
        """On resume the results are keyed by workflow key."""
        mock_task.properties = {
            "workflows": [{"key": "result1"}, {"key": "result2"}],
            "output_key": "parallel_results",
            "__subflow_keys__": {"proc_0": "result1", "proc_1": "result2"},
        }
        mock_context.subflow_results = [
            subflow_entry("proc_0", properties={"__output__": {"status": "done"}}),
            subflow_entry("proc_1", properties={"__output__": {"status": "done"}}),
        ]

        result = await ParallelSubworkflowsAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route is None
        results = mock_context.process.properties["parallel_results"]
        assert set(results) == {"result1", "result2"}
        assert results["result1"]["output"] == {"status": "done"}

    @pytest.mark.asyncio
    async def test_parallel_resume_partial_failure(self, mock_context, mock_task):
        """A failed child routes partial_failure; the task itself completes."""
        mock_task.properties = {
            "workflows": [{"key": "a"}, {"key": "b"}],
            "__subflow_keys__": {"proc_0": "a", "proc_1": "b"},
        }
        mock_context.subflow_results = [
            subflow_entry("proc_0"),
            subflow_entry("proc_1", success=False, error="b broke"),
        ]

        result = await ParallelSubworkflowsAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "partial_failure"
        assert result.output["b"] == {"success": False, "error": "b broke", "process_id": "proc_1"}

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
        """With fail_fast, no further workflow starts once one has failed."""
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

        # The first workflow fails during its inline run
        async def start_and_fail(process_id: str) -> None:
            mock_context.engine.started_processes.append(process_id)
            mock_store.processes[process_id].state = ProcessState.FAILED

        mock_context.engine.start_process = start_and_fail

        result = await ParallelSubworkflowsAction().run(mock_task, mock_context)

        assert result.suspend_children == ["proc_0"]
        assert len(mock_context.engine.created_processes) == 1

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

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        # Should still run the workflow it has (skipping missing definition)
        assert result.suspend_children == ["proc_0"]
        assert len(mock_context.engine.created_processes) == 1


class TestSubworkflowTimeoutAndEdgeCases:
    """Additional tests for timeout and edge cases."""

    @pytest.mark.asyncio
    async def test_subworkflow_timeout(self, mock_context, mock_task):
        """timeout bounds the child's inline run (start_process_with_timeout)."""
        mock_task.properties = {
            "workflow": {
                "id": "test",
                "name": "Test",
                "first_task_id": "t1",
                "tasks": {"t1": {"id": "t1", "name": "T1", "action": "test"}},
                "routings": [],
            },
            "wait": True,
            "timeout": 0.1,
        }

        result = await SubworkflowAction().run(mock_task, mock_context)

        assert mock_context.engine.start_timeouts == {"proc_0": 0.1}
        assert result.suspend_children == ["proc_0"]

    @pytest.mark.asyncio
    async def test_subworkflow_process_not_found(self, mock_context, mock_task):
        """A child that disappeared fails the task on resume."""
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
        mock_context.subflow_results = [
            subflow_entry("proc_0", success=False, error="Child process not found")
        ]

        result = await SubworkflowAction().run(mock_task, mock_context)

        assert result.success is False
        assert "not found" in result.error

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
    async def test_wait_timeout_is_ignored(self, mock_context, mock_task, mock_store, caplog):
        """wait_subworkflow's timeout is ignored with a warning; the child is bounded where
        it starts."""
        mock_store.processes["running_proc"] = child_of(
            mock_context, "running_proc", ProcessState.RUNNING
        )
        mock_task.properties = {"process_id": "running_proc", "timeout": 0.1}

        result = await WaitForSubworkflowAction().run(mock_task, mock_context)

        assert result.suspend_children == ["running_proc"]
        assert "ignores timeout" in caplog.text

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
        """timeout bounds each child's inline run."""
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

        result = await ParallelSubworkflowsAction().run(mock_task, mock_context)

        assert mock_context.engine.start_timeouts == {"proc_0": 0.1}
        assert result.suspend_children == ["proc_0"]

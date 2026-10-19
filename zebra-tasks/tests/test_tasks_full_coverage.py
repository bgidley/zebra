"""Additional tests to achieve 100% coverage in zebra-tasks."""

from unittest.mock import MagicMock

import pytest
from zebra.core.models import (
    TaskInstance,
    TaskState,
)

from zebra_tasks.llm.action import LLMCallAction


class TestLLMActionBuildMessages:
    """Tests for LLMCallAction._build_messages."""

    def test_build_messages_with_list_content(self):
        """Test building messages with non-string content (list)."""
        action = LLMCallAction()

        task = TaskInstance(
            id="task-1",
            process_id="proc-1",
            task_definition_id="t1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={
                "messages": [
                    {"role": "user", "content": ["part1", "part2"]},  # List content
                ],
            },
        )

        mock_context = MagicMock()
        mock_context.resolve_template = lambda x: x

        messages = action._build_messages(task, mock_context)
        assert len(messages) == 1
        assert messages[0].content == ["part1", "part2"]


class TestLLMActionProcessResponse:
    """Tests for LLMCallAction._process_response."""

    def test_process_response_json_with_generic_code_block(self):
        """Test processing JSON response in generic code block."""
        action = LLMCallAction()

        task = TaskInstance(
            id="task-1",
            process_id="proc-1",
            task_definition_id="t1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={"response_format": "json"},
        )

        # Response with generic code block (not json-specific)
        content = '```\n{"key": "value"}\n```'
        result = action._process_response(content, task)
        assert result == {"key": "value"}

    def test_process_response_json_parse_failure(self):
        """Test processing invalid JSON returns raw content."""
        action = LLMCallAction()

        task = TaskInstance(
            id="task-1",
            process_id="proc-1",
            task_definition_id="t1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={"response_format": "json"},
        )

        content = "not valid json at all"
        result = action._process_response(content, task)
        assert result == content  # Returns raw content on failure


class TestSubtaskWorkflowFileLoading:
    """Tests for workflow file loading in subtasks."""

    @pytest.mark.asyncio
    async def test_spawn_with_workflow_file(self, mock_context, mock_task):
        """Test loading workflow from file."""
        import os
        import tempfile

        from zebra_tasks.subtasks.spawn import SubworkflowAction

        # Create a temporary workflow file
        yaml_content = """
name: File Workflow
first_task_id: t1
tasks:
  t1:
    name: Task 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            mock_task.properties = {
                "workflow_file": temp_path,
                "wait": False,
            }

            action = SubworkflowAction()
            result = await action.run(mock_task, mock_context)

            assert result.success is True
        finally:
            os.unlink(temp_path)


class TestParallelWorkflowEdgeCases:
    """Tests for ParallelSubworkflowsAction edge cases."""

    @pytest.mark.asyncio
    async def test_parallel_with_workflow_file(self, mock_context, mock_task, mock_store):
        """Test parallel with workflow files."""
        import os
        import tempfile

        from zebra_tasks.subtasks.parallel import ParallelSubworkflowsAction

        yaml_content = """
name: Parallel File Workflow
first_task_id: t1
tasks:
  t1:
    name: Task 1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            mock_task.properties = {
                "workflows": [
                    {"workflow_file": temp_path, "key": "wf1"},
                ],
            }

            action = ParallelSubworkflowsAction()
            result = await action.run(mock_task, mock_context)

            assert result.suspend_children == ["proc_0"]
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_parallel_non_string_property_value(self, mock_context, mock_task, mock_store):
        """Test parallel with non-string property values."""
        from zebra_tasks.subtasks.parallel import ParallelSubworkflowsAction

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
                    "properties": {"count": 42, "enabled": True},  # Non-string values
                    "key": "wf1",
                },
            ],
        }

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        assert result.suspend_children == ["proc_0"]
        # Verify non-string properties were passed correctly
        created = mock_context.engine.created_processes[0]
        assert created.properties.get("count") == 42
        assert created.properties.get("enabled") is True

    @pytest.mark.asyncio
    async def test_parallel_process_failure(self, mock_context, mock_task, mock_store):
        """Test parallel when all workflows fail (on resume, #181)."""
        from zebra_tasks.subtasks.parallel import ParallelSubworkflowsAction

        mock_task.properties = {
            "workflows": [{"key": "wf1"}],
            "__subflow_keys__": {"proc_0": "wf1"},
        }
        mock_context.subflow_results = [
            {"process_id": "proc_0", "success": False, "error": "Failed", "properties": {}}
        ]

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        assert result.next_route == "partial_failure"
        assert result.output["wf1"]["error"] == "Failed"

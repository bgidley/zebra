"""Additional tests to achieve 100% coverage in zebra-tasks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.models import (
    ProcessState,
    TaskInstance,
    TaskState,
)

from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import (
    Message,
    ToolDefinition,
)
from zebra_tasks.llm.providers.registry import (
    _providers,
    _try_auto_register,
)


class TestLLMActionGetProvider:
    """Tests for LLMCallAction._get_provider."""

    def test_get_provider_from_task_properties(self):
        """Test getting provider from task properties."""
        action = LLMCallAction()

        task = TaskInstance(
            id="task-1",
            process_id="proc-1",
            task_definition_id="t1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={
                "provider": "test_provider",
                "model": "test_model",
            },
        )

        mock_context = MagicMock()
        mock_context.process.properties = {}

        # Mock the registry module
        mock_provider = MagicMock()
        with patch("zebra_tasks.llm.providers.registry.get_provider") as mock_get:
            mock_get.return_value = mock_provider

            # Call the internal method directly
            result = action._get_provider(task, mock_context)

            # Should have called get_provider with task properties
            mock_get.assert_called_once_with("test_provider", "test_model")
            assert result == mock_provider


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


class TestProviderRegistryAutoRegister:
    """Tests for provider auto-registration."""

    def test_try_auto_register_anthropic_import_error(self):
        """Test anthropic auto-register with import error."""
        _providers.clear()

        # Mock import failure
        with patch.dict("sys.modules", {"anthropic": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                _try_auto_register("anthropic")

        # Provider should not be registered
        assert "anthropic" not in _providers

    def test_try_auto_register_openai_import_error(self):
        """Test openai auto-register with import error."""
        _providers.clear()

        with patch.dict("sys.modules", {"openai": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                _try_auto_register("openai")

        assert "openai" not in _providers


class TestAnthropicProviderStreaming:
    """Tests for Anthropic provider streaming."""

    @pytest.fixture
    def mock_anthropic_stream(self):
        """Create mock for streaming."""
        mock_stream_context = MagicMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_stream_context)
        mock_stream_context.__aexit__ = AsyncMock()

        async def mock_text_stream():
            yield "Hello "
            yield "world!"

        mock_stream_context.text_stream = mock_text_stream()

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.stream = MagicMock(return_value=mock_stream_context)

        mock_module = MagicMock()
        mock_module.AsyncAnthropic = MagicMock(return_value=mock_client)

        return mock_module, mock_client

    @pytest.mark.asyncio
    async def test_anthropic_stream(self, mock_anthropic_stream):
        """Test Anthropic provider streaming."""
        mock_module, mock_client = mock_anthropic_stream

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                import importlib

                import zebra_tasks.llm.providers.anthropic as anthropic_provider

                importlib.reload(anthropic_provider)

                provider = anthropic_provider.AnthropicProvider()
                messages = [Message.user("Hello")]

                chunks = []
                async for chunk in provider.stream(messages):
                    chunks.append(chunk)

                assert len(chunks) == 2
                assert "".join(chunks) == "Hello world!"


class TestOpenAIProviderStreaming:
    """Tests for OpenAI provider streaming."""

    @pytest.fixture
    def mock_openai_stream(self):
        """Create mock for streaming."""

        async def mock_stream():
            chunk1 = MagicMock()
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta = MagicMock()
            chunk1.choices[0].delta.content = "Hello "
            yield chunk1

            chunk2 = MagicMock()
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta = MagicMock()
            chunk2.choices[0].delta.content = "world!"
            yield chunk2

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        mock_module = MagicMock()
        mock_module.AsyncOpenAI = MagicMock(return_value=mock_client)

        return mock_module, mock_client

    @pytest.mark.asyncio
    async def test_openai_stream(self, mock_openai_stream):
        """Test OpenAI provider streaming."""
        mock_module, mock_client = mock_openai_stream

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_module}):
                import importlib

                import zebra_tasks.llm.providers.openai as openai_provider

                importlib.reload(openai_provider)

                provider = openai_provider.OpenAIProvider()
                messages = [Message.user("Hello")]

                chunks = []
                async for chunk in provider.stream(messages):
                    chunks.append(chunk)

                assert len(chunks) == 2


class TestOpenAIProviderToolCalls:
    """Tests for OpenAI provider with tool calls."""

    @pytest.fixture
    def mock_openai_with_tools(self):
        """Create mock OpenAI with tool calls response."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-123"
        mock_tool_call.type = "function"
        mock_tool_call.function = MagicMock()
        mock_tool_call.function.name = "search"
        mock_tool_call.function.arguments = '{"query": "test"}'

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        mock_response.model = "gpt-4o"

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_module = MagicMock()
        mock_module.AsyncOpenAI = MagicMock(return_value=mock_client)

        return mock_module, mock_client

    @pytest.mark.asyncio
    async def test_openai_with_tool_calls(self, mock_openai_with_tools):
        """Test OpenAI provider returning tool calls."""
        mock_module, mock_client = mock_openai_with_tools

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_module}):
                import importlib

                import zebra_tasks.llm.providers.openai as openai_provider

                importlib.reload(openai_provider)

                provider = openai_provider.OpenAIProvider()
                messages = [Message.user("Search for test")]

                response = await provider.complete(messages)

                assert response.has_tool_calls
                assert response.tool_calls[0].name == "search"


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

            # Complete immediately
            async def complete():
                import asyncio

                await asyncio.sleep(0.02)
                for p in mock_store.processes.values():
                    p.state = ProcessState.COMPLETE

            import asyncio

            asyncio.create_task(complete())

            action = ParallelSubworkflowsAction()
            result = await action.run(mock_task, mock_context)

            assert result.success is True
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

        async def complete():
            import asyncio

            await asyncio.sleep(0.02)
            for p in mock_store.processes.values():
                p.state = ProcessState.COMPLETE

        import asyncio

        asyncio.create_task(complete())

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        # Verify non-string properties were passed correctly
        created = mock_context.engine.created_processes[0]
        assert created.properties.get("count") == 42
        assert created.properties.get("enabled") is True

    @pytest.mark.asyncio
    async def test_parallel_process_failure(self, mock_context, mock_task, mock_store):
        """Test parallel when all workflows fail."""
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
                    "key": "wf1",
                },
            ],
        }

        async def fail_all():
            import asyncio

            await asyncio.sleep(0.02)
            for p in mock_store.processes.values():
                p.state = ProcessState.FAILED
                p.properties["__error__"] = "Failed"

        import asyncio

        asyncio.create_task(fail_all())

        action = ParallelSubworkflowsAction()
        result = await action.run(mock_task, mock_context)

        # Should return failure or partial_failure route
        assert result.next_route in ("failure", "partial_failure")


class TestAnthropicStreamingWithTools:
    """Tests for Anthropic streaming with tools."""

    @pytest.fixture
    def mock_anthropic_stream_with_system(self):
        """Create mock for streaming with system prompt."""
        mock_stream_context = MagicMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_stream_context)
        mock_stream_context.__aexit__ = AsyncMock()

        async def mock_text_stream():
            yield "Response"

        mock_stream_context.text_stream = mock_text_stream()

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.stream = MagicMock(return_value=mock_stream_context)

        mock_module = MagicMock()
        mock_module.AsyncAnthropic = MagicMock(return_value=mock_client)

        return mock_module, mock_client

    @pytest.mark.asyncio
    async def test_anthropic_stream_with_system_and_tools(self, mock_anthropic_stream_with_system):
        """Test Anthropic streaming with system prompt and tools."""
        mock_module, mock_client = mock_anthropic_stream_with_system

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                import importlib

                import zebra_tasks.llm.providers.anthropic as anthropic_provider

                importlib.reload(anthropic_provider)

                provider = anthropic_provider.AnthropicProvider()
                messages = [
                    Message.system("Be helpful"),
                    Message.user("Hello"),
                ]
                tools = [
                    ToolDefinition(
                        name="search",
                        description="Search",
                        parameters={"type": "object"},
                    )
                ]

                chunks = []
                async for chunk in provider.stream(messages, tools=tools):
                    chunks.append(chunk)

                # Verify stream was called with tools
                call_kwargs = mock_client.messages.stream.call_args.kwargs
                assert "tools" in call_kwargs


class TestOpenAIStreamingEmpty:
    """Tests for OpenAI streaming with empty chunks."""

    @pytest.fixture
    def mock_openai_stream_empty(self):
        """Create mock for streaming with empty chunks."""

        async def mock_stream():
            # First chunk has no content
            chunk1 = MagicMock()
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta = MagicMock()
            chunk1.choices[0].delta.content = None
            yield chunk1

            # Second chunk has content
            chunk2 = MagicMock()
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta = MagicMock()
            chunk2.choices[0].delta.content = "Hello"
            yield chunk2

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        mock_module = MagicMock()
        mock_module.AsyncOpenAI = MagicMock(return_value=mock_client)

        return mock_module, mock_client

    @pytest.mark.asyncio
    async def test_openai_stream_skips_empty(self, mock_openai_stream_empty):
        """Test OpenAI streaming skips empty content chunks."""
        mock_module, mock_client = mock_openai_stream_empty

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_module}):
                import importlib

                import zebra_tasks.llm.providers.openai as openai_provider

                importlib.reload(openai_provider)

                provider = openai_provider.OpenAIProvider()
                messages = [Message.user("Hello")]

                chunks = []
                async for chunk in provider.stream(messages):
                    chunks.append(chunk)

                # Should only have one chunk (the non-empty one)
                assert len(chunks) == 1
                assert chunks[0] == "Hello"

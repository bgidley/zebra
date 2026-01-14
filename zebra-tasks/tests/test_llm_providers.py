"""Tests for LLM providers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from zebra_tasks.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from zebra_tasks.llm.providers.registry import (
    register_provider,
    get_provider,
    list_providers,
    _providers,
)


class TestMessage:
    """Tests for Message class."""

    def test_system_message(self):
        msg = Message.system("You are helpful")
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "You are helpful"

    def test_user_message(self):
        msg = Message.user("Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"

    def test_assistant_message(self):
        msg = Message.assistant("Hi there")
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Hi there"

    def test_assistant_with_tool_calls(self):
        tool_calls = [
            ToolCall(id="tc1", name="search", arguments={"query": "test"})
        ]
        msg = Message.assistant("Let me search", tool_calls=tool_calls)
        assert msg.tool_calls == tool_calls

    def test_tool_message(self):
        msg = Message.tool("Search result", tool_call_id="tc1", name="search")
        assert msg.role == MessageRole.TOOL
        assert msg.content == "Search result"
        assert msg.tool_call_id == "tc1"


class TestTokenUsage:
    """Tests for TokenUsage class."""

    def test_total_tokens(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_zero_tokens(self):
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        assert usage.total_tokens == 0


class TestLLMResponse:
    """Tests for LLMResponse class."""

    def test_has_tool_calls_true(self):
        response = LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="test", arguments={})],
            finish_reason="tool_use",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model="test-model",
        )
        assert response.has_tool_calls is True

    def test_has_tool_calls_false(self):
        response = LLMResponse(
            content="Hello",
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model="test-model",
        )
        assert response.has_tool_calls is False


class TestProviderRegistry:
    """Tests for provider registry."""

    def setup_method(self):
        """Clear registry before each test."""
        _providers.clear()

    def test_register_and_get_provider(self):
        """Test registering and retrieving a provider."""
        class TestProvider(LLMProvider):
            def __init__(self, model=None):
                self._model = model or "test"

            async def complete(self, messages, **kwargs):
                pass

            async def stream(self, messages, **kwargs):
                yield ""

            @property
            def name(self):
                return "test"

            @property
            def model(self):
                return self._model

            @property
            def max_context_tokens(self):
                return 10000

        register_provider("test", lambda m: TestProvider(m))

        provider = get_provider("test")
        assert provider.name == "test"

        provider_with_model = get_provider("test", "custom-model")
        assert provider_with_model.model == "custom-model"

    def test_get_unknown_provider_raises(self):
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_provider("nonexistent")

    def test_list_providers(self):
        """Test listing available providers."""
        class DummyProvider(LLMProvider):
            async def complete(self, messages, **kwargs):
                pass

            async def stream(self, messages, **kwargs):
                yield ""

            @property
            def name(self):
                return "dummy"

            @property
            def model(self):
                return "model"

            @property
            def max_context_tokens(self):
                return 1000

        register_provider("provider1", lambda m: DummyProvider())
        register_provider("provider2", lambda m: DummyProvider())

        providers = list_providers()
        assert "provider1" in providers
        assert "provider2" in providers

    def test_case_insensitive_provider_name(self):
        """Test that provider names are case insensitive."""
        class TestProvider(LLMProvider):
            async def complete(self, messages, **kwargs):
                pass

            async def stream(self, messages, **kwargs):
                yield ""

            @property
            def name(self):
                return "test"

            @property
            def model(self):
                return "model"

            @property
            def max_context_tokens(self):
                return 1000

        register_provider("MyProvider", lambda m: TestProvider())

        # Should work with any case
        assert get_provider("myprovider") is not None
        assert get_provider("MYPROVIDER") is not None
        assert get_provider("MyProvider") is not None


class TestAnthropicProvider:
    """Tests for Anthropic provider."""

    @pytest.fixture
    def mock_anthropic_module(self):
        """Create mock Anthropic module and client."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Test response")]
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        mock_module = MagicMock()
        mock_module.AsyncAnthropic = MagicMock(return_value=mock_client)

        return mock_module, mock_client

    @pytest.mark.asyncio
    async def test_complete_simple_message(self, mock_anthropic_module):
        """Test simple completion."""
        mock_module, mock_client = mock_anthropic_module

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                # Need to reimport to get the mocked version
                import importlib
                import zebra_tasks.llm.providers.anthropic as anthropic_provider
                importlib.reload(anthropic_provider)

                provider = anthropic_provider.AnthropicProvider()
                messages = [Message.user("Hello")]

                response = await provider.complete(messages)

                assert response.content == "Test response"
                assert response.usage.input_tokens == 100
                assert response.usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_system_message_extraction(self, mock_anthropic_module):
        """Test that system message is extracted properly."""
        mock_module, mock_client = mock_anthropic_module

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

                await provider.complete(messages)

                # Verify system was passed separately
                call_kwargs = mock_client.messages.create.call_args.kwargs
                assert call_kwargs["system"] == "Be helpful"
                assert len(call_kwargs["messages"]) == 1

    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        # Create a mock module that doesn't raise ImportError
        mock_module = MagicMock()

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=True):
            with patch.dict("sys.modules", {"anthropic": mock_module}):
                import importlib
                import zebra_tasks.llm.providers.anthropic as anthropic_provider
                importlib.reload(anthropic_provider)

                with pytest.raises(ValueError, match="API key required"):
                    anthropic_provider.AnthropicProvider()


class TestOpenAIProvider:
    """Tests for OpenAI provider."""

    @pytest.fixture
    def mock_openai_module(self):
        """Create mock OpenAI module and client."""
        mock_message = MagicMock()
        mock_message.content = "Test response"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o"

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_module = MagicMock()
        mock_module.AsyncOpenAI = MagicMock(return_value=mock_client)

        return mock_module, mock_client, mock_response

    @pytest.mark.asyncio
    async def test_complete_simple_message(self, mock_openai_module):
        """Test simple completion."""
        mock_module, mock_client, _ = mock_openai_module

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_module}):
                import importlib
                import zebra_tasks.llm.providers.openai as openai_provider
                importlib.reload(openai_provider)

                provider = openai_provider.OpenAIProvider()
                messages = [Message.user("Hello")]

                response = await provider.complete(messages)

                assert response.content == "Test response"
                assert response.usage.input_tokens == 100
                assert response.usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_tool_calls_parsing(self, mock_openai_module):
        """Test parsing of tool calls from response."""
        mock_module, mock_client, mock_response = mock_openai_module

        # Setup mock with tool calls
        mock_tool_call = MagicMock()
        mock_tool_call.id = "tc_123"
        mock_tool_call.function = MagicMock()
        mock_tool_call.function.name = "search"
        mock_tool_call.function.arguments = '{"query": "test"}'

        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.choices[0].message.content = None

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_module}):
                import importlib
                import zebra_tasks.llm.providers.openai as openai_provider
                importlib.reload(openai_provider)

                provider = openai_provider.OpenAIProvider()
                messages = [Message.user("Search for test")]

                response = await provider.complete(messages)

                assert response.has_tool_calls
                assert len(response.tool_calls) == 1
                assert response.tool_calls[0].name == "search"
                assert response.tool_calls[0].arguments == {"query": "test"}

    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        mock_module = MagicMock()

        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=True):
            with patch.dict("sys.modules", {"openai": mock_module}):
                import importlib
                import zebra_tasks.llm.providers.openai as openai_provider
                importlib.reload(openai_provider)

                with pytest.raises(ValueError, match="API key required"):
                    openai_provider.OpenAIProvider()


class TestToolDefinition:
    """Tests for ToolDefinition."""

    def test_tool_definition_creation(self):
        """Test creating a tool definition."""
        tool = ToolDefinition(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        )

        assert tool.name == "search"
        assert tool.description == "Search the web"
        assert "query" in tool.parameters["properties"]

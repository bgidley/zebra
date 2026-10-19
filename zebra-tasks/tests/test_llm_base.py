"""Tests for the LLM message, response and tool types."""

from zebra_tasks.llm.base import (
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
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
        tool_calls = [ToolCall(id="tc1", name="search", arguments={"query": "test"})]
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


class TestMessageFactoryMethods:
    """Test Message factory methods."""

    def test_message_with_empty_content(self):
        """Test message with empty content."""
        msg = Message.user("")
        assert msg.content == ""
        assert msg.role == MessageRole.USER

    def test_assistant_with_both_content_and_tools(self):
        """Test assistant message with both content and tool calls."""
        tool_calls = [ToolCall(id="tc1", name="test", arguments={})]
        msg = Message.assistant("Thinking...", tool_calls=tool_calls)

        assert msg.content == "Thinking..."
        assert len(msg.tool_calls) == 1


class TestLLMResponseModel:
    """Test LLMResponse model."""

    def test_response_with_raw_response(self):
        """Test LLMResponse with raw_response."""
        raw = {"id": "resp-123", "created": 12345}
        response = LLMResponse(
            content="Hello",
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model="test",
            raw_response=raw,
        )

        assert response.raw_response == raw

    def test_response_with_empty_tool_calls(self):
        """Test LLMResponse with empty tool calls list."""
        response = LLMResponse(
            content="Hello",
            tool_calls=[],
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model="test",
        )

        # Empty list should still be falsy for has_tool_calls
        assert response.has_tool_calls is False

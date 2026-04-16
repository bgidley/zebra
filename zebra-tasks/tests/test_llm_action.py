"""Tests for LLM call action."""


import pytest

from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
)


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, response_content: str = "Test response"):
        self.response_content = response_content
        self.calls: list[dict] = []

    async def complete(
        self,
        messages: list[Message],
        tools=None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences=None,
    ) -> LLMResponse:
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return LLMResponse(
            content=self.response_content,
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            model="mock-model",
        )

    async def stream(self, messages, **kwargs):
        yield self.response_content

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-model"

    @property
    def max_context_tokens(self) -> int:
        return 100000


class TestLLMCallAction:
    """Tests for LLMCallAction."""

    @pytest.fixture
    def mock_llm_provider(self):
        return MockLLMProvider()

    @pytest.fixture
    def llm_context(self, mock_context, mock_llm_provider):
        mock_context.process.properties["__llm_provider__"] = mock_llm_provider
        return mock_context

    @pytest.mark.asyncio
    async def test_simple_prompt(self, llm_context, mock_task):
        """Test simple prompt-based LLM call."""
        mock_task.properties = {
            "prompt": "What is 2 + 2?",
            "output_key": "answer",
        }

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        assert result.success is True
        assert llm_context.process.properties["answer"] == "Test response"

        # Verify LLM was called
        provider = llm_context.process.properties["__llm_provider__"]
        assert len(provider.calls) == 1
        assert provider.calls[0]["messages"][0].role == MessageRole.USER
        assert provider.calls[0]["messages"][0].content == "What is 2 + 2?"

    @pytest.mark.asyncio
    async def test_system_and_user_prompt(self, llm_context, mock_task):
        """Test with both system and user prompts."""
        mock_task.properties = {
            "system_prompt": "You are a math tutor.",
            "prompt": "Explain addition.",
            "output_key": "explanation",
        }

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        assert result.success is True

        provider = llm_context.process.properties["__llm_provider__"]
        messages = provider.calls[0]["messages"]
        assert len(messages) == 2
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[0].content == "You are a math tutor."
        assert messages[1].role == MessageRole.USER
        assert messages[1].content == "Explain addition."

    @pytest.mark.asyncio
    async def test_template_resolution(self, llm_context, mock_task):
        """Test template variable resolution in prompts."""
        llm_context.process.properties["user_name"] = "Alice"
        llm_context.process.properties["__task_output_prev_task"] = "previous result"

        mock_task.properties = {
            "prompt": "Hello {{user_name}}, the previous result was {{prev_task.output}}",
            "output_key": "greeting",
        }

        action = LLMCallAction()
        await action.run(mock_task, llm_context)

        provider = llm_context.process.properties["__llm_provider__"]
        prompt = provider.calls[0]["messages"][0].content
        assert "Hello Alice" in prompt
        assert "previous result" in prompt

    @pytest.mark.asyncio
    async def test_json_response_format(self, llm_context, mock_task):
        """Test JSON response parsing."""
        provider = llm_context.process.properties["__llm_provider__"]
        provider.response_content = '{"sentiment": "positive", "confidence": 0.95}'

        mock_task.properties = {
            "prompt": "Analyze sentiment",
            "response_format": "json",
            "output_key": "analysis",
        }

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        assert result.success is True
        analysis = llm_context.process.properties["analysis"]
        assert isinstance(analysis, dict)
        assert analysis["sentiment"] == "positive"
        assert analysis["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_json_in_markdown_code_block(self, llm_context, mock_task):
        """Test JSON extraction from markdown code block."""
        provider = llm_context.process.properties["__llm_provider__"]
        provider.response_content = '''Here's the analysis:
```json
{"result": "success", "value": 42}
```
That's the result.'''

        mock_task.properties = {
            "prompt": "Analyze",
            "response_format": "json",
            "output_key": "data",
        }

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        assert result.success is True
        data = llm_context.process.properties["data"]
        assert data["result"] == "success"
        assert data["value"] == 42

    @pytest.mark.asyncio
    async def test_custom_temperature_and_max_tokens(self, llm_context, mock_task):
        """Test custom temperature and max_tokens."""
        mock_task.properties = {
            "prompt": "Be creative",
            "temperature": 0.9,
            "max_tokens": 500,
        }

        action = LLMCallAction()
        await action.run(mock_task, llm_context)

        provider = llm_context.process.properties["__llm_provider__"]
        assert provider.calls[0]["temperature"] == 0.9
        assert provider.calls[0]["max_tokens"] == 500

    @pytest.mark.asyncio
    async def test_token_tracking(self, llm_context, mock_task):
        """Test that token usage is tracked."""
        mock_task.properties = {
            "prompt": "Count tokens",
            "output_key": "result",
        }

        action = LLMCallAction()
        await action.run(mock_task, llm_context)

        # Check total tokens tracked
        assert llm_context.process.properties["__total_tokens__"] == 150

        # Check usage metadata
        usage = llm_context.process.properties["result_usage"]
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate_tokens(self, llm_context, mock_task):
        """Test that multiple LLM calls accumulate token counts."""
        mock_task.properties = {"prompt": "Call 1"}

        action = LLMCallAction()
        await action.run(mock_task, llm_context)
        await action.run(mock_task, llm_context)
        await action.run(mock_task, llm_context)

        assert llm_context.process.properties["__total_tokens__"] == 450  # 150 * 3

        history = llm_context.process.properties["__token_history__"]
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_explicit_messages(self, llm_context, mock_task):
        """Test using explicit messages list."""
        mock_task.properties = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ],
            "output_key": "response",
        }

        action = LLMCallAction()
        await action.run(mock_task, llm_context)

        provider = llm_context.process.properties["__llm_provider__"]
        messages = provider.calls[0]["messages"]
        assert len(messages) == 4
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[3].content == "How are you?"

    @pytest.mark.asyncio
    async def test_no_provider_fails(self, mock_context, mock_task):
        """Test that missing provider fails gracefully."""
        mock_task.properties = {"prompt": "Test"}

        action = LLMCallAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No LLM provider" in result.error

    @pytest.mark.asyncio
    async def test_no_prompt_fails(self, llm_context, mock_task):
        """Test that missing prompt/messages fails."""
        mock_task.properties = {}

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        assert result.success is False
        assert "No prompt or messages" in result.error

    @pytest.mark.asyncio
    async def test_llm_error_handling(self, llm_context, mock_task):
        """Test error handling when LLM call fails."""
        provider = llm_context.process.properties["__llm_provider__"]

        async def raise_error(*args, **kwargs):
            raise Exception("API rate limit exceeded")

        provider.complete = raise_error

        mock_task.properties = {"prompt": "Test"}

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        assert result.success is False
        assert "rate limit" in result.error

    @pytest.mark.asyncio
    async def test_invalid_json_returns_raw(self, llm_context, mock_task):
        """Test that invalid JSON returns raw content."""
        provider = llm_context.process.properties["__llm_provider__"]
        provider.response_content = "This is not valid JSON {broken"

        mock_task.properties = {
            "prompt": "Get JSON",
            "response_format": "json",
            "output_key": "data",
        }

        action = LLMCallAction()
        result = await action.run(mock_task, llm_context)

        # Should succeed but return raw content
        assert result.success is True
        assert llm_context.process.properties["data"] == "This is not valid JSON {broken"

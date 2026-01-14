"""Integration tests for Anthropic provider using real API."""

import os
import pytest
from dotenv import load_dotenv

# Load .env before checking for API key
load_dotenv()

# Skip all tests if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)


class TestAnthropicIntegration:
    """Integration tests using real Anthropic API."""

    @pytest.mark.asyncio
    async def test_simple_completion(self):
        """Test a simple completion request."""
        from zebra_tasks.llm.providers import get_provider
        from zebra_tasks.llm.base import Message

        provider = get_provider("anthropic")
        response = await provider.complete([
            Message.user("Say 'hello' and nothing else.")
        ], max_tokens=50)

        assert response.content is not None
        assert "hello" in response.content.lower()
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0

    @pytest.mark.asyncio
    async def test_completion_with_system_prompt(self):
        """Test completion with system prompt."""
        from zebra_tasks.llm.providers import get_provider
        from zebra_tasks.llm.base import Message

        provider = get_provider("anthropic")
        response = await provider.complete([
            Message.system("You are a helpful assistant. Always respond in exactly 3 words."),
            Message.user("What is 2+2?"),
        ], max_tokens=50)

        assert response.content is not None
        # Should be a short response due to system prompt
        assert len(response.content.split()) <= 10

    @pytest.mark.asyncio
    async def test_streaming(self):
        """Test streaming completion."""
        from zebra_tasks.llm.providers import get_provider
        from zebra_tasks.llm.base import Message

        provider = get_provider("anthropic")
        chunks = []

        async for chunk in provider.stream([
            Message.user("Count from 1 to 5.")
        ], max_tokens=50):
            chunks.append(chunk)

        full_response = "".join(chunks)
        assert len(chunks) > 1  # Should have multiple chunks
        assert "1" in full_response
        assert "5" in full_response

    @pytest.mark.asyncio
    async def test_model_properties(self):
        """Test provider model properties."""
        from zebra_tasks.llm.providers import get_provider

        provider = get_provider("anthropic")

        assert provider.name == "anthropic"
        assert "claude" in provider.model
        assert provider.max_context_tokens > 0

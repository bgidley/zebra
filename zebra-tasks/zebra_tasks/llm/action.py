"""LLMCallAction - Task action for calling LLMs."""

from typing import Any
import json
import re

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

from zebra_tasks.llm.base import LLMProvider, Message, MessageRole, TokenUsage


class LLMCallAction(TaskAction):
    """
    TaskAction that calls an LLM provider.

    This action supports:
    - Simple prompt-based calls
    - Conversation history
    - Template variable resolution
    - JSON response parsing
    - Token tracking

    Properties:
        prompt: User prompt (supports {{var}} templates)
        system_prompt: System prompt (optional)
        messages: Full message history (alternative to prompt/system_prompt)
        temperature: LLM temperature (default: 0.7)
        max_tokens: Maximum response tokens (default: 4096)
        response_format: Expected format - "text", "json" (default: "text")
        json_schema: JSON schema for structured output (optional)
        output_key: Where to store response (default: "llm_response")
        provider: Provider name override (default: use __llm_provider__)
        model: Model name override (optional)

    Special process properties used:
        __llm_provider__: LLMProvider instance to use
        __total_tokens__: Running total of tokens used (updated)

    Example workflow usage:
        ```yaml
        tasks:
          analyze:
            name: "Analyze Text"
            action: llm_call
            properties:
              system_prompt: "You are a helpful analyst."
              prompt: "Analyze this text: {{input_text}}"
              temperature: 0.3
              output_key: analysis

          classify:
            name: "Classify Result"
            action: llm_call
            properties:
              prompt: |
                Based on this analysis: {{analysis}}
                Classify the sentiment as positive, negative, or neutral.
                Respond with JSON: {"sentiment": "...", "confidence": 0.0-1.0}
              response_format: json
              output_key: classification
        ```
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute the LLM call."""
        # Get LLM provider
        provider = self._get_provider(task, context)
        if provider is None:
            return TaskResult.fail("No LLM provider available")

        # Build messages
        messages = self._build_messages(task, context)
        if not messages:
            return TaskResult.fail("No prompt or messages provided")

        # Get parameters
        temperature = task.properties.get("temperature", 0.7)
        max_tokens = task.properties.get("max_tokens", 4096)

        try:
            # Call LLM
            response = await provider.complete(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Track token usage
            self._track_tokens(context, response.usage)

            # Process response
            content = response.content or ""
            output = self._process_response(content, task)

            # Store result
            output_key = task.properties.get("output_key", "llm_response")
            context.set_process_property(output_key, output)

            # Also store metadata
            context.set_process_property(f"{output_key}_usage", {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": response.model,
            })

            return TaskResult.ok(output={
                "response": output,
                "tokens_used": response.usage.total_tokens,
                "model": response.model,
            })

        except Exception as e:
            return TaskResult.fail(f"LLM call failed: {str(e)}")

    def _get_provider(
        self, task: TaskInstance, context: ExecutionContext
    ) -> LLMProvider | None:
        """Get the LLM provider to use."""
        from zebra_tasks.llm.providers.registry import get_provider

        # Check for provider in task properties first
        provider_name = task.properties.get("provider")
        model = task.properties.get("model")

        # Fall back to process properties
        if not provider_name:
            provider_name = context.process.properties.get("__llm_provider_name__")
        if not model:
            model = context.process.properties.get("__llm_model__")

        # If we have a provider name, create the provider
        if provider_name:
            return get_provider(provider_name, model)

        # Legacy: check for provider object (not recommended)
        return context.process.properties.get("__llm_provider__")

    def _build_messages(
        self, task: TaskInstance, context: ExecutionContext
    ) -> list[Message]:
        """Build message list from task properties."""
        # Check for explicit messages
        messages_prop = task.properties.get("messages")
        if messages_prop:
            messages = []
            for msg in messages_prop:
                role = MessageRole(msg.get("role", "user"))
                content = msg.get("content", "")
                if isinstance(content, str):
                    content = context.resolve_template(content)
                messages.append(Message(role=role, content=content))
            return messages

        # Build from prompt/system_prompt
        messages = []

        system_prompt = task.properties.get("system_prompt")
        if system_prompt:
            resolved = context.resolve_template(system_prompt)
            messages.append(Message.system(resolved))

        prompt = task.properties.get("prompt")
        if prompt:
            resolved = context.resolve_template(prompt)
            messages.append(Message.user(resolved))

        return messages

    def _process_response(self, content: str, task: TaskInstance) -> Any:
        """Process response based on expected format."""
        response_format = task.properties.get("response_format", "text")

        if response_format == "json":
            # Try to extract JSON from response
            try:
                extracted = self._extract_json(content)
                return json.loads(extracted)
            except (json.JSONDecodeError, ValueError):
                # Return raw content if JSON parsing fails
                return content

        return content

    def _extract_json(self, content: str) -> str:
        """Extract JSON from content, handling code blocks."""
        # Try to extract from code blocks using regex
        patterns = [
            r'```json\s*(.*?)\s*```',  # ```json ... ```
            r'```\s*(.*?)\s*```',       # ``` ... ```
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
        return content

    def _track_tokens(self, context: ExecutionContext, usage: TokenUsage) -> None:
        """Track token usage in process properties."""
        current = context.get_process_property("__total_tokens__", 0)
        context.set_process_property("__total_tokens__", current + usage.total_tokens)

        # Also track per-task breakdown
        token_history = context.get_process_property("__token_history__", [])
        token_history.append({
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "total": usage.total_tokens,
        })
        context.set_process_property("__token_history__", token_history)

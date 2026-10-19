"""LLMCallAction - Task action for calling LLMs."""

import json
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message, MessageRole
from zebra_tasks.llm.client import get_llm, model_for


class LLMCallAction(TaskAction):
    """
    TaskAction that calls an LLM.

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
        model: Tier (low / medium / high / max) or OpenRouter vendor/model slug;
            default the process's __llm_model__, else medium

    Special process properties used:
        __llm_model__: The run's model tier
        __total_tokens__ / __total_cost__ / __token_history__: Usage (updated)

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

    description = "Call an LLM to generate text or structured responses."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="prompt",
            type="string",
            description="User prompt text (supports {{var}} templates)",
            required=False,
        ),
        ParameterDef(
            name="system_prompt",
            type="string",
            description="System prompt to set LLM behavior",
            required=False,
        ),
        ParameterDef(
            name="messages",
            type="list[dict]",
            description="Full message history as list of {role, content} dicts",
            required=False,
        ),
        ParameterDef(
            name="temperature",
            type="float",
            description="LLM temperature (0.0-2.0, higher = more creative)",
            required=False,
            default=0.7,
        ),
        ParameterDef(
            name="max_tokens",
            type="int",
            description="Maximum tokens in response",
            required=False,
            default=4096,
        ),
        ParameterDef(
            name="response_format",
            type="string",
            description="Expected response format: 'text' or 'json'",
            required=False,
            default="text",
        ),
        ParameterDef(
            name="json_schema",
            type="dict",
            description="JSON schema for structured output validation",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the response",
            required=False,
            default="llm_response",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="Tier (low / medium / high / max) or OpenRouter vendor/model slug",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="response",
            type="any",
            description="LLM response (string or parsed JSON dict)",
            required=True,
        ),
        ParameterDef(
            name="tokens_used",
            type="int",
            description="Total tokens used in this call",
            required=True,
        ),
        ParameterDef(
            name="model",
            type="string",
            description="Model that was used for the completion",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute the LLM call."""
        # Build messages
        messages = self._build_messages(task, context)
        if not messages:
            return TaskResult.fail("No prompt or messages provided")

        # Get parameters
        temperature = task.properties.get("temperature", 0.7)
        max_tokens = task.properties.get("max_tokens", 4096)

        try:
            response = await get_llm(model_for(task, context), context).complete(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )


            # Process response
            content = response.content or ""
            output = self._process_response(content, task)

            # Store result
            output_key = task.properties.get("output_key", "llm_response")
            context.set_process_property(output_key, output)

            # Also store metadata
            context.set_process_property(
                f"{output_key}_usage",
                {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "model": response.model,
                },
            )

            return TaskResult.ok(
                output={
                    "response": output,
                    "tokens_used": response.usage.total_tokens,
                    "model": response.model,
                }
            )

        except Exception as e:
            return TaskResult.fail(f"LLM call failed: {str(e)}")

    def _build_messages(self, task: TaskInstance, context: ExecutionContext) -> list[Message]:
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
            r"```json\s*(.*?)\s*```",  # ```json ... ```
            r"```\s*(.*?)\s*```",  # ``` ... ```
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
        return content

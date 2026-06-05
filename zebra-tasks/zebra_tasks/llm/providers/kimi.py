"""Kimi (Moonshot AI) LLM provider.

Kimi exposes an OpenAI-compatible API at https://api.moonshot.cn/v1.
Set KIMI_API_KEY environment variable.
"""

import os

from zebra_tasks.llm.providers.openai import OpenAIProvider


class KimiProvider(OpenAIProvider):
    """LLM provider for Kimi (Moonshot AI) models.

    Uses the OpenAI-compatible endpoint at api.moonshot.cn.
    Set KIMI_API_KEY environment variable or pass api_key.
    """

    DEFAULT_MODEL = "moonshot-v1-32k"
    BASE_URL = "https://api.moonshot.cn/v1"

    CONTEXT_WINDOWS = {
        "moonshot-v1-8k": 8000,
        "moonshot-v1-32k": 32000,
        "moonshot-v1-128k": 128000,
        "moonshot-v1-auto": 128000,
        # Kimi k1.5 / k2 series (latest)
        "kimi-k1.5-8k": 8000,
        "kimi-k1.5-32k": 32000,
        "kimi-k2": 128000,
    }

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")

        resolved_model = model or self.DEFAULT_MODEL
        resolved_key = api_key or os.environ.get("KIMI_API_KEY")

        if not resolved_key:
            raise ValueError("Kimi API key required. Set KIMI_API_KEY or pass api_key.")

        import openai

        self._model = resolved_model
        self._api_key = resolved_key
        self._client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self.BASE_URL,
        )

    @property
    def name(self) -> str:
        return "kimi"

    @property
    def max_context_tokens(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, 32000)

"""Kimi (Moonshot AI) LLM provider.

Supports both the international platform (platform.kimi.ai) and the
Chinese domestic API (api.moonshot.cn). The base URL is selected via the
KIMI_BASE_URL environment variable.

Default: https://api.moonshot.ai/v1  (international, platform.kimi.ai keys)
China:   https://api.moonshot.cn/v1  (set KIMI_BASE_URL to override)

Set KIMI_API_KEY environment variable.
"""

import os

from zebra_tasks.llm.providers.openai import OpenAIProvider


class KimiProvider(OpenAIProvider):
    """LLM provider for Kimi (Moonshot AI) models.

    Uses the international endpoint by default (platform.kimi.ai keys).
    Set KIMI_BASE_URL=https://api.moonshot.cn/v1 for China domestic keys.
    Set KIMI_API_KEY environment variable or pass api_key.

    Current Kimi models are reasoning models that only accept a fixed temperature
    (1 with thinking on, 0.6 with it off), so the caller's temperature is never sent.
    Thinking is turned off where the model allows it: fast replies, and reasoning
    tokens don't use up ``max_tokens`` (#164).
    """

    DEFAULT_MODEL = "kimi-k2.6"
    BASE_URL = "https://api.moonshot.ai/v1"

    CONTEXT_WINDOWS = {
        "kimi-k2.6": 262144,
        "kimi-k3": 1048576,
        "kimi-k2.7-code": 262144,
        "kimi-k2.7-code-highspeed": 262144,
    }

    # Models that reject thinking={"type": "disabled"} (thinking is always on).
    THINKING_ONLY_MODELS = {"kimi-k2.7-code", "kimi-k2.7-code-highspeed"}

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")

        from zebra_tasks.llm.models import KIMI_MODELS

        resolved_model = KIMI_MODELS.get(model or "", model) or self.DEFAULT_MODEL
        resolved_key = api_key or os.environ.get("KIMI_API_KEY")
        resolved_base_url = os.environ.get("KIMI_BASE_URL", self.BASE_URL)

        if not resolved_key:
            raise ValueError("Kimi API key required. Set KIMI_API_KEY or pass api_key.")

        import openai

        self._model = resolved_model
        self._api_key = resolved_key
        self._client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=resolved_base_url,
        )

    @property
    def name(self) -> str:
        return "kimi"

    @property
    def max_context_tokens(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, 262144)

    def _sampling_kwargs(self, temperature: float) -> dict:
        """No temperature (fixed per model); disable thinking where the model allows it."""
        if self._model in self.THINKING_ONLY_MODELS:
            return {}
        return {"extra_body": {"thinking": {"type": "disabled"}}}

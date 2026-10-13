"""OpenRouter LLM provider.

OpenRouter (https://openrouter.ai) exposes hundreds of models from many vendors
behind one OpenAI-compatible API. Model ids are ``vendor/model`` slugs, e.g.
``anthropic/claude-sonnet-5.5`` or ``moonshotai/kimi-k3``.

Set OPENROUTER_API_KEY. Optional: OPENROUTER_MODEL (default model),
OPENROUTER_BASE_URL (override endpoint).
"""

import logging
import os

from zebra_tasks.llm.base import LLMResponse
from zebra_tasks.llm.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(OpenAIProvider):
    """LLM provider for any model served by OpenRouter.

    ``haiku`` / ``sonnet`` / ``opus`` map to the matching Claude 5.5 model on OpenRouter,
    raw ``vendor/model`` slugs pass through, and anything else (e.g. a ``claude-*`` id
    from a workflow written for Anthropic) falls back to the default model.

    OpenRouter reports the real USD cost of each call; it is carried on
    ``TokenUsage.cost_usd`` so cost tracking needs no price table (#182).
    """

    DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_CONTEXT_WINDOW = 128000

    CONTEXT_WINDOWS = {
        "anthropic/claude-haiku-5.5": 1000000,
        "anthropic/claude-sonnet-5.5": 1000000,
        "anthropic/claude-opus-5.5": 1000000,
        "moonshotai/kimi-k3": 1048576,
        "moonshotai/kimi-k2.6": 262144,
    }

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        try:
            import openai
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")

        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not resolved_key:
            raise ValueError("OpenRouter API key required. Set OPENROUTER_API_KEY or pass api_key.")

        self._model = self.resolve_model(model)
        self._api_key = resolved_key
        self._client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", self.BASE_URL),
            default_headers={"X-Title": "Zebra"},
        )

    @classmethod
    def resolve_model(cls, model: str | None) -> str:
        """Map a tier name, an ``openrouter`` alias or a raw slug to an OpenRouter model id."""
        from zebra_tasks.llm.models import ANTHROPIC_MODELS, OPENROUTER_TIER_MODELS

        model = (model or "").strip()
        tier = {v: k for k, v in ANTHROPIC_MODELS.items()}.get(model, model)
        if tier in OPENROUTER_TIER_MODELS:
            return OPENROUTER_TIER_MODELS[tier]
        if "/" in model:
            return model
        default = os.environ.get("OPENROUTER_MODEL") or cls.DEFAULT_MODEL
        if model not in ("", "openrouter"):
            logger.warning("OpenRouter has no model %r; using %s", model, default)
        return default

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def max_context_tokens(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, self.DEFAULT_CONTEXT_WINDOW)

    def _convert_response(self, response) -> LLMResponse:
        """Add OpenRouter's reported cost to the usage."""
        result = super()._convert_response(response)
        cost = getattr(response.usage, "cost", None)
        if cost is not None:
            result.usage.cost_usd = float(cost)
        return result

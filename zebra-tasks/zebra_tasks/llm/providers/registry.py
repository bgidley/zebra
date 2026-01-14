"""Provider registry for LLM providers."""

from typing import Callable
from zebra_tasks.llm.base import LLMProvider

# Registry of provider factories
_providers: dict[str, Callable[[str | None], LLMProvider]] = {}

# Track if we've loaded dotenv
_dotenv_loaded = False


def register_provider(name: str, factory: Callable[[str | None], LLMProvider]) -> None:
    """Register an LLM provider factory.

    Args:
        name: Provider name (e.g., 'anthropic', 'openai')
        factory: Callable that takes optional model name and returns LLMProvider
    """
    _providers[name.lower()] = factory


def get_provider(name: str, model: str | None = None) -> LLMProvider:
    """Get an LLM provider instance.

    Args:
        name: Provider name (e.g., 'anthropic', 'openai')
        model: Optional model name override

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If provider not found
    """
    # Lazily load environment variables from .env file
    global _dotenv_loaded
    if not _dotenv_loaded:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # dotenv not installed, skip
        _dotenv_loaded = True

    name_lower = name.lower()

    if name_lower not in _providers:
        # Try to auto-register known providers
        _try_auto_register(name_lower)

    if name_lower not in _providers:
        available = list(_providers.keys())
        raise ValueError(
            f"Unknown LLM provider: {name}. Available: {available}"
        )

    return _providers[name_lower](model)


def _try_auto_register(name: str) -> None:
    """Try to auto-register a known provider."""
    if name == "anthropic":
        try:
            from zebra_tasks.llm.providers.anthropic import AnthropicProvider
            register_provider("anthropic", lambda m: AnthropicProvider(model=m))
        except ImportError:
            pass
    elif name == "openai":
        try:
            from zebra_tasks.llm.providers.openai import OpenAIProvider
            register_provider("openai", lambda m: OpenAIProvider(model=m))
        except ImportError:
            pass


def list_providers() -> list[str]:
    """List available provider names."""
    return list(_providers.keys())

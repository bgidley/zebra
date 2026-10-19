"""Get an LLM: the one entry point for every LLM call (#205).

``get_llm(model, context)`` returns an LLM for a tier (``low`` / ``medium`` / ``high``
/ ``max``) or an exact OpenRouter ``vendor/model`` slug. Given the task's execution
context, every call it makes adds its tokens and cost to that process and to the
spend ledger (#206). ``model_for`` picks the model a task should use. Tests swap the
backend with ``set_llm_factory``.
"""

from collections.abc import Callable
from typing import Any

from zebra_tasks.llm.base import LLMProvider, LLMResponse
from zebra_tasks.llm.models import normalize_model
from zebra_tasks.llm.usage import record_spend, record_usage

LLMFactory = Callable[[str], LLMProvider]

_factory: LLMFactory | None = None


def get_llm(model: str | None = None, context: Any = None) -> LLMProvider:
    """An LLM for *model* (a tier or ``vendor/model`` slug; default the medium tier).

    With *context* (a task's ``ExecutionContext``), each call's usage is recorded on
    its process (``__total_cost__``, ``__total_tokens__``, ``__token_history__``).
    """
    resolved = normalize_model(model)
    if _factory is not None:
        llm = _factory(resolved)
    else:
        from zebra_tasks.llm.openrouter import OpenRouterLLM

        llm = OpenRouterLLM(resolved)
    return llm if context is None else _Recorded(llm, context)


def set_llm_factory(factory: LLMFactory | None) -> LLMFactory | None:
    """Make ``get_llm`` build LLMs with *factory* (None restores OpenRouter).

    Returns the previous factory. For tests and local tooling.
    """
    global _factory
    previous, _factory = _factory, factory
    return previous


def model_for(task: Any, context: Any, default: str | None = None) -> str:
    """The model a task uses: its ``model`` property, else the process's
    ``__llm_model__``, else *default*, else the medium tier."""
    return normalize_model(
        task.properties.get("model") or context.process.properties.get("__llm_model__") or default
    )


class _Recorded(LLMProvider):
    """An LLM whose calls record their usage on a task's process."""

    def __init__(self, llm: LLMProvider, context: Any):
        self._llm = llm
        self._context = context

    @property
    def model(self) -> str:
        return self._llm.model

    async def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        response = await self._llm.complete(*args, **kwargs)
        record_usage(self._context, response)
        await record_spend(self._context, response)
        return response

"""Get an LLM: the one entry point for every LLM call (#205).

``get_llm(model, context)`` returns an LLM for a tier (``low`` / ``medium`` / ``high``
/ ``max``) or an exact model (an OpenRouter ``vendor/model`` slug, or a Bedrock ID), from
the provider ``ZEBRA_LLM_PROVIDER`` names (``openrouter``, the default, or ``bedrock``,
#335). Given the task's execution context, every call it makes adds its tokens and cost
to that process and to the spend ledger (#206). ``model_for`` picks the model a task
should use. Tests swap the backend with ``set_llm_factory``.

Hard cost caps (#276): before each call a process whose ``__cost_cap_usd__`` property is set
is refused once its ``__total_cost__`` has reached it, and an ``__llm_guard__`` engine extra
(an async ``(process) -> reason | None``) may refuse it too. A refusal raises
``LLMCostCapExceeded`` and spends nothing.
"""

from collections.abc import Callable
from typing import Any

from zebra_tasks.llm.base import LLMProvider, LLMResponse
from zebra_tasks.llm.models import llm_provider, normalize_model
from zebra_tasks.llm.usage import record_spend, record_usage

LLMFactory = Callable[[str], LLMProvider]

#: Process property: the most this process may spend on LLM calls, in USD (#276).
COST_CAP_KEY = "__cost_cap_usd__"
#: Engine extra: ``async (process) -> str | None``; a reason refuses the call (#276).
LLM_GUARD_KEY = "__llm_guard__"


class LLMCostCapExceeded(RuntimeError):
    """An LLM call refused before it was made: the process is over its cost cap."""


_factory: LLMFactory | None = None


def get_llm(model: str | None = None, context: Any = None) -> LLMProvider:
    """An LLM for *model* (a tier or exact model; default the medium tier).

    With *context* (a task's ``ExecutionContext``), each call's usage is recorded on
    its process (``__total_cost__``, ``__total_tokens__``, ``__token_history__``).
    """
    resolved = normalize_model(model)
    if _factory is not None:
        llm = _factory(resolved)
    elif llm_provider() == "bedrock":
        from zebra_tasks.llm.bedrock import BedrockLLM

        llm = BedrockLLM(resolved)
    else:
        from zebra_tasks.llm.openrouter import OpenRouterLLM

        llm = OpenRouterLLM(resolved)
    return llm if context is None else _Recorded(llm, context)


def set_llm_factory(factory: LLMFactory | None) -> LLMFactory | None:
    """Make ``get_llm`` build LLMs with *factory* (None restores the configured provider).

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
        await check_cost_cap(self._context)
        response = await self._llm.complete(*args, **kwargs)
        record_usage(self._context, response)
        await record_spend(self._context, response)
        return response


async def check_cost_cap(context: Any) -> None:
    """Raise ``LLMCostCapExceeded`` if *context*'s process may not make another LLM call.

    Checks the process's own ``__cost_cap_usd__`` against its ``__total_cost__``, then the
    engine's ``__llm_guard__`` extra, if any. Without either it allows the call.
    """
    process = getattr(context, "process", None)
    props = getattr(process, "properties", None)
    props = props if isinstance(props, dict) else {}
    cap = props.get(COST_CAP_KEY)
    if cap is not None:
        try:
            cap_usd = float(cap)
        except (TypeError, ValueError):
            cap_usd = 0.0  # an unreadable cap fails closed
        spent = float(props.get("__total_cost__") or 0)
        if spent >= cap_usd:
            raise LLMCostCapExceeded(
                f"LLM cost cap reached: spent ${spent:.4f} of ${cap_usd:.4f} for this process"
            )
    extras = getattr(context, "extras", None)
    guard = extras.get(LLM_GUARD_KEY) if isinstance(extras, dict) else None
    if guard is not None and process is not None:
        reason = await guard(process)
        if reason:
            raise LLMCostCapExceeded(reason)

"""Record an LLM call's tokens and cost on its process (#205).

OpenRouter reports each call's USD cost (``TokenUsage.cost_usd``). Every action that
calls an LLM records it here, so ``__total_cost__`` (which the budget daemon and
goal cost reporting read), ``__total_tokens__`` and ``__token_history__`` stay
consistent.
"""

import asyncio
import logging

from zebra.tasks.base import ExecutionContext

from zebra_tasks.llm.base import LLMResponse

logger = logging.getLogger(__name__)


def record_usage(context: ExecutionContext, response: LLMResponse) -> float:
    """Add *response*'s tokens and cost to the process; return the call's cost."""
    usage = response.usage
    cost = usage.cost_usd or 0.0
    context.set_process_property(
        "__total_tokens__", context.get_process_property("__total_tokens__", 0) + usage.total_tokens
    )
    total = context.get_process_property("__total_cost__", 0.0) + cost
    context.set_process_property("__total_cost__", total)
    history = context.get_process_property("__token_history__", [])
    history.append(
        {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "total": usage.total_tokens,
            "cost": cost,
            "model": response.model,
        }
    )
    context.set_process_property("__token_history__", history)

    # Soft per-goal budget warning, when the BudgetManager is injected.
    budget_manager = context.extras.get("__budget_manager__")
    if budget_manager is not None:
        try:
            asyncio.get_running_loop().create_task(budget_manager.check_and_warn(total))
        except Exception:  # noqa: BLE001 - a warning must never fail the LLM call
            logger.debug("Budget warning skipped", exc_info=True)
    return cost

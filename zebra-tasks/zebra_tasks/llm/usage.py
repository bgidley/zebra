"""Record an LLM call's tokens and cost (#205, #206).

OpenRouter reports each call's USD cost (``TokenUsage.cost_usd``). ``record_usage``
adds it to the calling process (``__total_cost__``, ``__total_tokens__``,
``__token_history__``); ``record_spend`` appends it to the metrics store's spend
ledger, which the daily budget sums, so every call counts once wherever it ran.
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


async def record_spend(context: ExecutionContext, response: LLMResponse) -> None:
    """Append *response*'s cost to the spend ledger of the injected metrics store (#206).

    A ledger failure is logged, never raised: it must not fail the LLM call.
    """
    metrics = context.extras.get("__metrics_store__")
    if metrics is None:
        return
    usage = response.usage
    try:
        await metrics.record_llm_spend(
            cost=usage.cost_usd or 0.0,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model=response.model or "",
            process_id=getattr(context.process, "id", None),
        )
    except Exception:  # noqa: BLE001 - spend bookkeeping never fails the call
        logger.warning("Could not record LLM spend", exc_info=True)

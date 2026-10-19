"""In-memory spend ledger, run totals and record_run_totals (#206)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from zebra_agent.metrics import WorkflowRun, record_run_totals
from zebra_agent.storage.interfaces import MetricsStore
from zebra_agent.storage.metrics import InMemoryMetricsStore


async def test_budget_sums_the_ledger_not_run_costs():
    store = InMemoryMetricsStore()
    reset = datetime.now(UTC) - timedelta(hours=1)
    run = WorkflowRun.create("W", "goal")
    run.cost = 9.99  # run records no longer drive the budget
    run.completed_at = datetime.now(UTC)
    await store.record_run(run)
    await store.record_llm_spend(cost=1.0, at=reset - timedelta(seconds=1))
    await store.record_llm_spend(cost=0.25)
    await store.record_llm_spend(cost=0.5, model="m", process_id="p")

    assert await store.get_total_cost_since(reset) == pytest.approx(0.75)


async def test_record_run_totals_sets_the_root_process_spend():
    store = InMemoryMetricsStore()
    run = WorkflowRun.create("W", "goal")
    await store.record_run(run)
    process = SimpleNamespace(
        properties={
            "run_id": run.id,
            "__total_cost__": 0.038,
            "__token_history__": [{"input": 100, "output": 20}, {"input": 50, "output": 5}],
        }
    )

    assert await record_run_totals(store, process)

    stored = await store.get_run(run.id)
    assert stored.cost == pytest.approx(0.038)
    assert (stored.input_tokens, stored.output_tokens, stored.tokens_used) == (150, 25, 175)


async def test_record_run_totals_without_a_run_or_store():
    store = InMemoryMetricsStore()
    assert not await record_run_totals(store, SimpleNamespace(properties={"run_id": "nope"}))
    assert not await record_run_totals(store, SimpleNamespace(properties={}))
    assert not await record_run_totals(None, SimpleNamespace(properties={"run_id": "x"}))


async def test_record_run_totals_never_raises():
    class Broken(InMemoryMetricsStore):
        async def update_run_totals(self, run_id, **kwargs):
            raise RuntimeError("db down")

    assert not await record_run_totals(Broken(), SimpleNamespace(properties={"run_id": "x"}))


async def test_base_store_defaults_keep_custom_stores_working():
    """A MetricsStore subclass without a ledger still works (O4)."""
    assert "record_llm_spend" not in MetricsStore.__abstractmethods__
    assert "update_run_totals" not in MetricsStore.__abstractmethods__
    store = InMemoryMetricsStore()
    assert await MetricsStore.update_run_totals(store, "r", cost=1.0) is False
    assert await MetricsStore.record_llm_spend(store, cost=1.0) is None

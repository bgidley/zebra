"""LLM spend ledger and run totals in the Django metrics store; daemon finish hook (#206)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from zebra.core.models import ProcessState
from zebra_agent_web.api.models import WorkflowRunModel
from zebra_agent_web.metrics_store import DjangoMetricsStore


@pytest.mark.django_db(transaction=True)
async def test_budget_sums_the_ledger_since_the_reset():
    store = DjangoMetricsStore()
    reset = datetime.now(UTC) - timedelta(hours=1)
    await store.record_llm_spend(cost=0.5, model="old", at=reset - timedelta(minutes=5))
    await store.record_llm_spend(cost=0.012345678, input_tokens=10, output_tokens=5, model="a/b")
    await store.record_llm_spend(cost=0.25, process_id="p1")

    assert await store.get_total_cost_since(reset) == pytest.approx(0.262345678)


@pytest.mark.django_db(transaction=True)
async def test_run_totals_overwrite_the_recorded_cost():
    store = DjangoMetricsStore()
    await sync_to_async(WorkflowRunModel.objects.create)(
        id="run-1",
        workflow_name="Basic Hello",
        goal="Count",
        started_at=datetime.now(UTC),
        cost=0,
    )

    assert await store.update_run_totals("run-1", cost=0.03799, input_tokens=900, output_tokens=100)
    assert not await store.update_run_totals("no-such-run", cost=1.0)

    run = await store.get_run("run-1")
    assert run.cost == pytest.approx(0.03799)
    assert (run.input_tokens, run.output_tokens, run.tokens_used) == (900, 100, 1000)


@pytest.mark.django_db(transaction=True)
async def test_daemon_records_a_finished_goals_full_spend():
    from zebra_agent_web.api import daemon

    store = DjangoMetricsStore()
    await sync_to_async(WorkflowRunModel.objects.create)(
        id="run-2", workflow_name="W", goal="g", started_at=datetime.now(UTC), cost=0
    )
    process = SimpleNamespace(
        id="proc-2",
        state=ProcessState.COMPLETE,
        properties={
            "run_id": "run-2",
            "__total_cost__": 0.038,
            "__token_history__": [{"input": 100, "output": 20}, {"input": 50, "output": 5}],
        },
    )
    engine = SimpleNamespace(extras={"__metrics_store__": store})

    await daemon._record_finished(process, engine, None)

    run = await store.get_run("run-2")
    assert run.cost == pytest.approx(0.038)
    assert run.tokens_used == 175

"""LLM spend ledger and run totals in the Django metrics store; daemon finish hook (#206)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from zebra.core.models import ProcessState
from zebra.storage.memory import InMemoryStore
from zebra_agent_web.api.models import WorkflowRunModel
from zebra_agent_web.metrics_store import DjangoMetricsStore


@pytest.mark.django_db(transaction=True)
async def test_budget_sums_the_ledger_from_the_reset_instant():
    store = DjangoMetricsStore()
    reset = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    await store.record_llm_spend(cost=0.5, model="old", at=reset - timedelta(seconds=1))
    await store.record_llm_spend(cost=0.1, at=reset)
    await store.record_llm_spend(cost=0.012345678, input_tokens=10, output_tokens=5, model="a/b")
    await store.record_llm_spend(cost=0.25, process_id="p1")

    assert await store.get_total_cost_since(reset) == pytest.approx(0.362345678)


@pytest.mark.django_db(transaction=True)
async def test_spend_for_processes_and_run_totals():
    store = DjangoMetricsStore()
    await store.record_llm_spend(cost=0.03, input_tokens=100, output_tokens=20, process_id="root")
    await store.record_llm_spend(cost=0.008, input_tokens=40, output_tokens=4, process_id="kid")
    await store.record_llm_spend(cost=9.0, process_id="other")
    await sync_to_async(WorkflowRunModel.objects.create)(
        id="run-1", workflow_name="W", goal="g", started_at=datetime.now(UTC), cost=0
    )

    totals = await store.get_spend_for_processes(["root", "kid"])
    assert totals[0] == pytest.approx(0.038) and totals[1:] == (140, 24)
    assert await store.update_run_totals("run-1", cost=0.038, input_tokens=140, output_tokens=24)
    assert not await store.update_run_totals("no-such-run", cost=1.0)

    run = await store.get_run("run-1")
    assert run.cost == pytest.approx(0.038)
    assert (run.input_tokens, run.output_tokens, run.tokens_used) == (140, 24, 164)


@pytest.mark.django_db(transaction=True)
async def test_daemon_records_a_finished_goals_full_spend():
    from zebra_agent_web.api import daemon

    metrics = DjangoMetricsStore()
    await sync_to_async(WorkflowRunModel.objects.create)(
        id="run-2", workflow_name="W", goal="g", started_at=datetime.now(UTC), cost=0
    )
    await metrics.record_llm_spend(cost=0.03, input_tokens=100, output_tokens=20, process_id="p2")
    process = SimpleNamespace(id="p2", state=ProcessState.COMPLETE, properties={"run_id": "run-2"})
    engine = SimpleNamespace(extras={"__metrics_store__": metrics}, store=InMemoryStore())

    await daemon._record_finished(process, engine, None)

    run = await metrics.get_run("run-2")
    assert run.cost == pytest.approx(0.03)
    assert run.tokens_used == 120

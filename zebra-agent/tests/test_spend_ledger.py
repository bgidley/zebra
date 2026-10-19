"""Spend ledger, budget and run totals (#206)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory
from zebra_tasks.subtasks.spawn import SubworkflowAction

from zebra_agent.metrics import WorkflowRun, record_run_totals
from zebra_agent.storage.interfaces import MetricsStore
from zebra_agent.storage.metrics import InMemoryMetricsStore


class PaidLLM(LLMProvider):
    """Every call costs $0.25 and 10 + 5 tokens, as OpenRouter would report."""

    model = "low"

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        return LLMResponse(
            content="ok",
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(10, 5, cost_usd=0.25),
            model="vendor/picked",
        )


def _llm_task(task_id: str) -> TaskDefinition:
    return TaskDefinition(id=task_id, name=task_id, action="llm_call", properties={"prompt": "hi"})


CHILD = ProcessDefinition(
    id="child", name="Child", first_task_id="think", tasks={"think": _llm_task("think")}
)

PARENT = ProcessDefinition(
    id="parent",
    name="Parent",
    first_task_id="plan",
    tasks={
        "plan": _llm_task("plan"),
        "delegate": TaskDefinition(
            id="delegate",
            name="Delegate",
            action="subworkflow",
            properties={"workflow": CHILD.model_dump(mode="json")},
        ),
        "review": _llm_task("review"),
    },
    routings=[
        RoutingDefinition(id="r1", source_task_id="plan", dest_task_id="delegate"),
        RoutingDefinition(id="r2", source_task_id="delegate", dest_task_id="review"),
    ],
)


async def test_budget_ledger_and_run_totals_agree_across_a_process_tree():
    """O2/O3: budget == ledger sum == every process's own spend, counted once."""
    set_llm_factory(lambda model: PaidLLM())
    metrics = InMemoryMetricsStore()
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("llm_call", LLMCallAction)
    registry.register_action("subworkflow", SubworkflowAction)
    store = InMemoryStore()
    engine = WorkflowEngine(store, registry, extras={"__metrics_store__": metrics})
    run = WorkflowRun.create("Parent", "goal")
    await metrics.record_run(run)
    start = datetime.now(UTC) - timedelta(seconds=1)

    process = await engine.create_process(PARENT, properties={"run_id": run.id})
    await engine.start_process(process.id)
    process = await store.load_process(process.id)
    (child,) = await store.list_child_processes(process.id)

    # Three calls: two in the parent, one in the subflow. The child inherits the
    # parent's properties (its __total_cost__ includes the parent's first call), so
    # only the ledger, which holds each call once, gives the true total.
    assert process.properties["__total_cost__"] == pytest.approx(0.5)
    assert child.parent_process_id == process.id
    assert await metrics.get_total_cost_since(start) == pytest.approx(0.75)

    assert await record_run_totals(metrics, store, process)
    stored = await metrics.get_run(run.id)
    assert stored.cost == pytest.approx(0.75)
    assert (stored.input_tokens, stored.output_tokens) == (30, 15)


async def test_budget_counts_spend_from_the_reset_instant():
    store = InMemoryMetricsStore()
    reset = datetime(2026, 10, 19, tzinfo=UTC)
    await store.record_llm_spend(cost=1.0, at=reset - timedelta(microseconds=1))
    await store.record_llm_spend(cost=0.25, at=reset)
    await store.record_llm_spend(cost=0.5, at=reset + timedelta(hours=1))

    assert await store.get_total_cost_since(reset) == pytest.approx(0.75)


async def test_run_records_no_longer_drive_the_budget():
    store = InMemoryMetricsStore()
    run = WorkflowRun.create("W", "goal")
    run.cost = 9.99
    run.completed_at = datetime.now(UTC)
    await store.record_run(run)

    assert await store.get_total_cost_since(datetime.now(UTC) - timedelta(hours=1)) == 0.0


async def test_run_totals_fall_back_without_a_ledger():
    """A store with no ledger: root cost plus the goal workflow's reported cost."""

    class NoLedger(InMemoryMetricsStore):
        async def get_spend_for_processes(self, process_ids):
            return None

    metrics = NoLedger()
    run = WorkflowRun.create("W", "goal")
    await metrics.record_run(run)
    process = SimpleNamespace(
        id="root",
        properties={
            "run_id": run.id,
            "__total_cost__": 0.03,
            "__token_history__": [{"input": 100, "output": 20}],
            "execution_result": {"cost": 0.008, "input_tokens": 40, "output_tokens": 4},
        },
    )

    assert await record_run_totals(metrics, InMemoryStore(), process)

    stored = await metrics.get_run(run.id)
    assert stored.cost == pytest.approx(0.038)
    assert (stored.input_tokens, stored.output_tokens) == (140, 24)


async def test_record_run_totals_without_a_run_or_store():
    store = InMemoryMetricsStore()
    process = SimpleNamespace(id="p", properties={"run_id": "nope"})
    assert not await record_run_totals(store, InMemoryStore(), process)
    assert not await record_run_totals(store, None, SimpleNamespace(id="p", properties={}))
    assert not await record_run_totals(None, None, process)


async def test_record_run_totals_never_raises():
    class Broken(InMemoryMetricsStore):
        async def update_run_totals(self, run_id, **kwargs):
            raise RuntimeError("db down")

    process = SimpleNamespace(id="p", properties={"run_id": "x"})
    assert not await record_run_totals(Broken(), InMemoryStore(), process)


def test_new_methods_are_optional_for_custom_stores():
    """O4: a MetricsStore without a ledger still satisfies the interface."""
    for name in ("record_llm_spend", "update_run_totals", "get_spend_for_processes"):
        assert name not in MetricsStore.__abstractmethods__

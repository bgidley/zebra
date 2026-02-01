"""Performance tests for the Zebra workflow engine.

These tests mirror the Rust performance tests in zebra-rs/tests/test_performance.rs
to enable cross-language performance comparison.

The database comparison tests require environment variables:
- PostgreSQL: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
- Oracle: ORACLE_USERNAME, ORACLE_PASSWORD, ORACLE_DSN
"""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import pytest

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.storage.base import StateStore
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry


class PerfAction(TaskAction):
    """A lightweight action for performance testing."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Simulate minimal work
        return TaskResult.ok(output={"status": "done"})


def create_sequential_workflow(num_tasks: int) -> ProcessDefinition:
    """Create a workflow definition with a configurable number of sequential tasks."""
    tasks: dict[str, TaskDefinition] = {}
    routings: list[RoutingDefinition] = []

    for i in range(num_tasks):
        task_id = f"task_{i}"
        tasks[task_id] = TaskDefinition(
            id=task_id,
            name=f"Task {i}",
            action="perf",
        )

        if i > 0:
            prev_task_id = f"task_{i - 1}"
            routings.append(
                RoutingDefinition(
                    id=f"r_{i}",
                    source_task_id=prev_task_id,
                    dest_task_id=task_id,
                )
            )

    return ProcessDefinition(
        id="perf_sequential",
        name="Performance Sequential",
        first_task_id="task_0",
        tasks=tasks,
        routings=routings,
    )


def create_parallel_workflow(num_branches: int) -> ProcessDefinition:
    """Create a workflow with parallel branches that join."""
    tasks: dict[str, TaskDefinition] = {}
    routings: list[RoutingDefinition] = []

    # Start task
    tasks["start"] = TaskDefinition(id="start", name="Start", action="perf")

    # Parallel branches
    for i in range(num_branches):
        branch_id = f"branch_{i}"
        tasks[branch_id] = TaskDefinition(
            id=branch_id,
            name=f"Branch {i}",
            action="perf",
        )
        routings.append(
            RoutingDefinition(
                id=f"r_start_{i}",
                source_task_id="start",
                dest_task_id=branch_id,
                parallel=True,
            )
        )
        routings.append(
            RoutingDefinition(
                id=f"r_join_{i}",
                source_task_id=branch_id,
                dest_task_id="join",
            )
        )

    # Join task
    tasks["join"] = TaskDefinition(
        id="join",
        name="Join",
        synchronized=True,
        action="perf",
    )

    # End task
    tasks["end"] = TaskDefinition(id="end", name="End", action="perf")
    routings.append(
        RoutingDefinition(
            id="r_end",
            source_task_id="join",
            dest_task_id="end",
        )
    )

    return ProcessDefinition(
        id="perf_parallel",
        name="Performance Parallel",
        first_task_id="start",
        tasks=tasks,
        routings=routings,
    )


def create_engine(store: StateStore | None = None) -> WorkflowEngine:
    """Create a workflow engine with performance action registered."""
    if store is None:
        store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_action("perf", PerfAction)
    return WorkflowEngine(store, registry)


@dataclass
class PerfResult:
    """Performance test result."""

    store_name: str
    test_name: str
    num_workflows: int
    tasks_per_workflow: int
    total_tasks: int
    elapsed_seconds: float
    workflows_per_second: float
    tasks_per_second: float
    avg_workflow_ms: float

    def __str__(self) -> str:
        return (
            f"{self.store_name}: {self.elapsed_seconds:.3f}s | "
            f"{self.workflows_per_second:.1f} wf/s | "
            f"{self.tasks_per_second:.1f} tasks/s | "
            f"{self.avg_workflow_ms:.2f}ms/wf"
        )


async def run_perf_test(
    engine: WorkflowEngine,
    definition: ProcessDefinition,
    num_workflows: int,
    tasks_per_workflow: int,
    store_name: str,
    test_name: str,
) -> PerfResult:
    """Run a performance test and return results."""
    # Pre-save the definition
    await engine.store.save_definition(definition)

    completed = 0

    async def run_workflow(workflow_index: int) -> None:
        nonlocal completed
        process = await engine.create_process(definition)
        await engine.start_process(process.id)
        completed += 1

    start = time.perf_counter()

    # Run all workflows in parallel
    await asyncio.gather(*[run_workflow(i) for i in range(num_workflows)])

    elapsed = time.perf_counter() - start

    return PerfResult(
        store_name=store_name,
        test_name=test_name,
        num_workflows=num_workflows,
        tasks_per_workflow=tasks_per_workflow,
        total_tasks=completed * tasks_per_workflow,
        elapsed_seconds=elapsed,
        workflows_per_second=completed / elapsed,
        tasks_per_second=(completed * tasks_per_workflow) / elapsed,
        avg_workflow_ms=(elapsed / num_workflows) * 1000,
    )


class TestPerformance:
    """Performance test suite mirroring Rust tests."""

    @pytest.mark.asyncio
    async def test_perf_100_parallel_workflows_sequential_tasks(self):
        """Execute 100 workflows in parallel, each with 10 sequential tasks.

        Measures:
        - Total completion time
        - Workflows per second throughput
        - Tasks per second throughput
        - Average time per workflow
        """
        NUM_WORKFLOWS = 100
        TASKS_PER_WORKFLOW = 10

        engine = create_engine()
        definition = create_sequential_workflow(TASKS_PER_WORKFLOW)

        # Pre-save the definition
        await engine.store.save_definition(definition)

        completed = 0

        async def run_workflow(workflow_index: int) -> None:
            nonlocal completed
            process = await engine.create_process(definition)
            await engine.start_process(process.id)
            completed += 1

        start = time.perf_counter()

        # Run all workflows in parallel
        await asyncio.gather(*[run_workflow(i) for i in range(NUM_WORKFLOWS)])

        elapsed = time.perf_counter() - start

        print(f"\n=== Performance Test: 100 Parallel Workflows (Sequential Tasks) ===")
        print(f"Workflows completed: {completed}")
        print(f"Tasks per workflow: {TASKS_PER_WORKFLOW}")
        print(f"Total tasks executed: {completed * TASKS_PER_WORKFLOW}")
        print(f"Total time: {elapsed:.3f}s")
        print(f"Workflows per second: {completed / elapsed:.2f}")
        print(f"Tasks per second: {(completed * TASKS_PER_WORKFLOW) / elapsed:.2f}")
        print(f"Average time per workflow: {(elapsed / NUM_WORKFLOWS) * 1000:.2f}ms")

        assert completed == NUM_WORKFLOWS

    @pytest.mark.asyncio
    async def test_perf_100_parallel_workflows_with_branching(self):
        """Execute 100 workflows in parallel, each with parallel branching.

        Each workflow has: start task + 5 parallel branches + join + end tasks (8 total).

        Measures:
        - Workflows completed
        - Tasks per second
        - Workflows per second
        - Average time per workflow
        """
        NUM_WORKFLOWS = 100
        BRANCHES_PER_WORKFLOW = 5

        engine = create_engine()
        definition = create_parallel_workflow(BRANCHES_PER_WORKFLOW)

        # Pre-save the definition
        await engine.store.save_definition(definition)

        completed = 0

        async def run_workflow(workflow_index: int) -> None:
            nonlocal completed
            process = await engine.create_process(definition)
            await engine.start_process(process.id)
            completed += 1

        start = time.perf_counter()

        # Run all workflows in parallel
        await asyncio.gather(*[run_workflow(i) for i in range(NUM_WORKFLOWS)])

        elapsed = time.perf_counter() - start

        # Tasks: start + branches + join + end = 1 + branches + 1 + 1 = branches + 3
        tasks_per_workflow = BRANCHES_PER_WORKFLOW + 3

        print(f"\n=== Performance Test: 100 Parallel Workflows (With Branching) ===")
        print(f"Workflows completed: {completed}")
        print(f"Branches per workflow: {BRANCHES_PER_WORKFLOW}")
        print(f"Tasks per workflow: {tasks_per_workflow}")
        print(f"Total tasks executed: {completed * tasks_per_workflow}")
        print(f"Total time: {elapsed:.3f}s")
        print(f"Workflows per second: {completed / elapsed:.2f}")
        print(f"Tasks per second: {(completed * tasks_per_workflow) / elapsed:.2f}")
        print(f"Average time per workflow: {(elapsed / NUM_WORKFLOWS) * 1000:.2f}ms")

        assert completed == NUM_WORKFLOWS

    @pytest.mark.asyncio
    async def test_perf_1000_workflows_quick(self):
        """Stress test with 1000 workflows.

        Each workflow has 5 sequential tasks for a total of 5000 task executions.

        Measures throughput metrics under higher load.
        """
        NUM_WORKFLOWS = 1000
        TASKS_PER_WORKFLOW = 5

        engine = create_engine()
        definition = create_sequential_workflow(TASKS_PER_WORKFLOW)

        # Pre-save the definition
        await engine.store.save_definition(definition)

        completed = 0

        async def run_workflow(workflow_index: int) -> None:
            nonlocal completed
            process = await engine.create_process(definition)
            await engine.start_process(process.id)
            completed += 1

        start = time.perf_counter()

        # Run all workflows in parallel
        await asyncio.gather(*[run_workflow(i) for i in range(NUM_WORKFLOWS)])

        elapsed = time.perf_counter() - start

        print(f"\n=== Performance Test: 1000 Workflows (Quick) ===")
        print(f"Workflows completed: {completed}")
        print(f"Tasks per workflow: {TASKS_PER_WORKFLOW}")
        print(f"Total tasks executed: {completed * TASKS_PER_WORKFLOW}")
        print(f"Total time: {elapsed:.3f}s")
        print(f"Workflows per second: {completed / elapsed:.2f}")
        print(f"Tasks per second: {(completed * TASKS_PER_WORKFLOW) / elapsed:.2f}")

        assert completed == NUM_WORKFLOWS


# =============================================================================
# Database Comparison Tests: Oracle vs PostgreSQL vs InMemory
# =============================================================================


def has_postgres_config() -> bool:
    """Check if PostgreSQL configuration is available."""
    return bool(os.environ.get("PGHOST") or os.environ.get("PGDATABASE"))


def has_oracle_config() -> bool:
    """Check if Oracle configuration is available."""
    return bool(
        os.environ.get("ORACLE_USERNAME")
        and os.environ.get("ORACLE_PASSWORD")
        and os.environ.get("ORACLE_DSN")
    )


async def create_postgres_store() -> StateStore:
    """Create and initialize a PostgreSQL store."""
    from zebra.storage.postgres import PostgreSQLStore

    store = PostgreSQLStore(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        database=os.environ.get("PGDATABASE", "zebra_perf_test"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD"),
    )
    await store.initialize()
    return store


async def create_oracle_store() -> StateStore:
    """Create and initialize an Oracle store."""
    from zebra.storage.oracle import OracleStore

    store = OracleStore(
        user=os.environ.get("ORACLE_USERNAME"),
        password=os.environ.get("ORACLE_PASSWORD"),
        dsn=os.environ.get("ORACLE_DSN"),
        wallet_location=os.environ.get("ORACLE_WALLET_LOCATION"),
        wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD"),
    )
    await store.initialize()
    return store


@pytest.mark.skipif(
    not (has_postgres_config() or has_oracle_config()),
    reason="No database configuration available (set PGHOST/ORACLE_* env vars)",
)
class TestDatabaseComparison:
    """Compare performance across different storage backends."""

    @pytest.mark.asyncio
    async def test_compare_sequential_workflows(self):
        """Compare sequential workflow performance across storage backends.

        Runs 50 workflows with 10 sequential tasks each on:
        - InMemory (baseline)
        - PostgreSQL (if configured)
        - Oracle (if configured)
        """
        NUM_WORKFLOWS = 50
        TASKS_PER_WORKFLOW = 10

        definition = create_sequential_workflow(TASKS_PER_WORKFLOW)
        results: list[PerfResult] = []

        # Test 1: InMemory (baseline)
        print("\n" + "=" * 70)
        print("DATABASE COMPARISON: Sequential Workflows")
        print(f"Workflows: {NUM_WORKFLOWS} | Tasks/workflow: {TASKS_PER_WORKFLOW}")
        print("=" * 70)

        memory_store = InMemoryStore()
        memory_engine = create_engine(memory_store)
        result = await run_perf_test(
            memory_engine,
            definition,
            NUM_WORKFLOWS,
            TASKS_PER_WORKFLOW,
            "InMemory",
            "sequential",
        )
        results.append(result)
        print(f"\n  InMemory:   {result}")

        # Test 2: PostgreSQL (if available)
        if has_postgres_config():
            try:
                pg_store = await create_postgres_store()
                pg_engine = create_engine(pg_store)
                result = await run_perf_test(
                    pg_engine,
                    definition,
                    NUM_WORKFLOWS,
                    TASKS_PER_WORKFLOW,
                    "PostgreSQL",
                    "sequential",
                )
                results.append(result)
                print(f"  PostgreSQL: {result}")
                await pg_store.close()
            except Exception as e:
                print(f"  PostgreSQL: SKIPPED ({e})")

        # Test 3: Oracle (if available)
        if has_oracle_config():
            try:
                oracle_store = await create_oracle_store()
                oracle_engine = create_engine(oracle_store)
                result = await run_perf_test(
                    oracle_engine,
                    definition,
                    NUM_WORKFLOWS,
                    TASKS_PER_WORKFLOW,
                    "Oracle",
                    "sequential",
                )
                results.append(result)
                print(f"  Oracle:     {result}")
                await oracle_store.close()
            except Exception as e:
                print(f"  Oracle:     SKIPPED ({e})")

        # Print comparison summary
        if len(results) > 1:
            baseline = results[0]  # InMemory
            print("\n  Comparison (vs InMemory baseline):")
            for r in results[1:]:
                ratio = r.elapsed_seconds / baseline.elapsed_seconds
                print(
                    f"    {r.store_name}: {ratio:.1f}x slower ({r.tasks_per_second:.1f} vs {baseline.tasks_per_second:.1f} tasks/s)"
                )

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_compare_parallel_workflows(self):
        """Compare parallel workflow performance across storage backends.

        Runs 50 workflows with 5 parallel branches each on:
        - InMemory (baseline)
        - PostgreSQL (if configured)
        - Oracle (if configured)
        """
        NUM_WORKFLOWS = 50
        BRANCHES_PER_WORKFLOW = 5
        TASKS_PER_WORKFLOW = BRANCHES_PER_WORKFLOW + 3  # start + branches + join + end

        definition = create_parallel_workflow(BRANCHES_PER_WORKFLOW)
        results: list[PerfResult] = []

        print("\n" + "=" * 70)
        print("DATABASE COMPARISON: Parallel Workflows (with branching)")
        print(
            f"Workflows: {NUM_WORKFLOWS} | Branches: {BRANCHES_PER_WORKFLOW} | Tasks/workflow: {TASKS_PER_WORKFLOW}"
        )
        print("=" * 70)

        # Test 1: InMemory (baseline)
        memory_store = InMemoryStore()
        memory_engine = create_engine(memory_store)
        result = await run_perf_test(
            memory_engine,
            definition,
            NUM_WORKFLOWS,
            TASKS_PER_WORKFLOW,
            "InMemory",
            "parallel",
        )
        results.append(result)
        print(f"\n  InMemory:   {result}")

        # Test 2: PostgreSQL (if available)
        if has_postgres_config():
            try:
                pg_store = await create_postgres_store()
                pg_engine = create_engine(pg_store)
                result = await run_perf_test(
                    pg_engine,
                    definition,
                    NUM_WORKFLOWS,
                    TASKS_PER_WORKFLOW,
                    "PostgreSQL",
                    "parallel",
                )
                results.append(result)
                print(f"  PostgreSQL: {result}")
                await pg_store.close()
            except Exception as e:
                print(f"  PostgreSQL: SKIPPED ({e})")

        # Test 3: Oracle (if available)
        if has_oracle_config():
            try:
                oracle_store = await create_oracle_store()
                oracle_engine = create_engine(oracle_store)
                result = await run_perf_test(
                    oracle_engine,
                    definition,
                    NUM_WORKFLOWS,
                    TASKS_PER_WORKFLOW,
                    "Oracle",
                    "parallel",
                )
                results.append(result)
                print(f"  Oracle:     {result}")
                await oracle_store.close()
            except Exception as e:
                print(f"  Oracle:     SKIPPED ({e})")

        # Print comparison summary
        if len(results) > 1:
            baseline = results[0]  # InMemory
            print("\n  Comparison (vs InMemory baseline):")
            for r in results[1:]:
                ratio = r.elapsed_seconds / baseline.elapsed_seconds
                print(
                    f"    {r.store_name}: {ratio:.1f}x slower ({r.tasks_per_second:.1f} vs {baseline.tasks_per_second:.1f} tasks/s)"
                )

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_compare_high_volume(self):
        """Compare high-volume workflow performance across storage backends.

        Runs 200 workflows with 5 sequential tasks each on:
        - InMemory (baseline)
        - PostgreSQL (if configured)
        - Oracle (if configured)

        This tests sustained throughput under higher load.
        """
        NUM_WORKFLOWS = 200
        TASKS_PER_WORKFLOW = 5

        definition = create_sequential_workflow(TASKS_PER_WORKFLOW)
        results: list[PerfResult] = []

        print("\n" + "=" * 70)
        print("DATABASE COMPARISON: High Volume")
        print(f"Workflows: {NUM_WORKFLOWS} | Tasks/workflow: {TASKS_PER_WORKFLOW}")
        print(f"Total tasks: {NUM_WORKFLOWS * TASKS_PER_WORKFLOW}")
        print("=" * 70)

        # Test 1: InMemory (baseline)
        memory_store = InMemoryStore()
        memory_engine = create_engine(memory_store)
        result = await run_perf_test(
            memory_engine,
            definition,
            NUM_WORKFLOWS,
            TASKS_PER_WORKFLOW,
            "InMemory",
            "high_volume",
        )
        results.append(result)
        print(f"\n  InMemory:   {result}")

        # Test 2: PostgreSQL (if available)
        if has_postgres_config():
            try:
                pg_store = await create_postgres_store()
                pg_engine = create_engine(pg_store)
                result = await run_perf_test(
                    pg_engine,
                    definition,
                    NUM_WORKFLOWS,
                    TASKS_PER_WORKFLOW,
                    "PostgreSQL",
                    "high_volume",
                )
                results.append(result)
                print(f"  PostgreSQL: {result}")
                await pg_store.close()
            except Exception as e:
                print(f"  PostgreSQL: SKIPPED ({e})")

        # Test 3: Oracle (if available)
        if has_oracle_config():
            try:
                oracle_store = await create_oracle_store()
                oracle_engine = create_engine(oracle_store)
                result = await run_perf_test(
                    oracle_engine,
                    definition,
                    NUM_WORKFLOWS,
                    TASKS_PER_WORKFLOW,
                    "Oracle",
                    "high_volume",
                )
                results.append(result)
                print(f"  Oracle:     {result}")
                await oracle_store.close()
            except Exception as e:
                print(f"  Oracle:     SKIPPED ({e})")

        # Print comparison summary
        if len(results) > 1:
            baseline = results[0]  # InMemory
            print("\n  Comparison (vs InMemory baseline):")
            for r in results[1:]:
                ratio = r.elapsed_seconds / baseline.elapsed_seconds
                print(
                    f"    {r.store_name}: {ratio:.1f}x slower ({r.tasks_per_second:.1f} vs {baseline.tasks_per_second:.1f} tasks/s)"
                )

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_oracle_vs_postgres_direct(self):
        """Direct comparison between Oracle and PostgreSQL only.

        Runs 100 workflows with 10 sequential tasks each.
        Skips if either database is not configured.
        """
        if not has_postgres_config():
            pytest.skip("PostgreSQL not configured")
        if not has_oracle_config():
            pytest.skip("Oracle not configured")

        NUM_WORKFLOWS = 100
        TASKS_PER_WORKFLOW = 10

        definition = create_sequential_workflow(TASKS_PER_WORKFLOW)

        print("\n" + "=" * 70)
        print("DIRECT COMPARISON: Oracle vs PostgreSQL")
        print(f"Workflows: {NUM_WORKFLOWS} | Tasks/workflow: {TASKS_PER_WORKFLOW}")
        print("=" * 70)

        # PostgreSQL
        pg_store = await create_postgres_store()
        pg_engine = create_engine(pg_store)
        pg_result = await run_perf_test(
            pg_engine,
            definition,
            NUM_WORKFLOWS,
            TASKS_PER_WORKFLOW,
            "PostgreSQL",
            "direct_comparison",
        )
        await pg_store.close()
        print(f"\n  PostgreSQL: {pg_result}")

        # Oracle
        oracle_store = await create_oracle_store()
        oracle_engine = create_engine(oracle_store)
        oracle_result = await run_perf_test(
            oracle_engine,
            definition,
            NUM_WORKFLOWS,
            TASKS_PER_WORKFLOW,
            "Oracle",
            "direct_comparison",
        )
        await oracle_store.close()
        print(f"  Oracle:     {oracle_result}")

        # Comparison
        print("\n  Results:")
        if oracle_result.elapsed_seconds < pg_result.elapsed_seconds:
            speedup = pg_result.elapsed_seconds / oracle_result.elapsed_seconds
            print(f"    Oracle is {speedup:.2f}x faster than PostgreSQL")
        else:
            speedup = oracle_result.elapsed_seconds / pg_result.elapsed_seconds
            print(f"    PostgreSQL is {speedup:.2f}x faster than Oracle")

        print(f"\n  Throughput comparison:")
        print(f"    PostgreSQL: {pg_result.tasks_per_second:.1f} tasks/sec")
        print(f"    Oracle:     {oracle_result.tasks_per_second:.1f} tasks/sec")

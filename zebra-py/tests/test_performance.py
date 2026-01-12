"""Performance tests for the Zebra workflow engine.

These tests mirror the Rust performance tests in zebra-rs/tests/test_performance.rs
to enable cross-language performance comparison.
"""

import asyncio
import time
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


def create_engine() -> WorkflowEngine:
    """Create a workflow engine with performance action registered."""
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_action("perf", PerfAction)
    return WorkflowEngine(store, registry)


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

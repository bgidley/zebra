"""Pytest fixtures for zebra-tasks tests."""

import pytest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
    RoutingDefinition,
)
from zebra.tasks.base import ExecutionContext


@dataclass
class MockStore:
    """Mock StateStore for testing."""

    processes: dict[str, ProcessInstance] = field(default_factory=dict)
    definitions: dict[str, ProcessDefinition] = field(default_factory=dict)

    async def load_process(self, process_id: str) -> ProcessInstance | None:
        return self.processes.get(process_id)

    async def save_process(self, process: ProcessInstance) -> None:
        self.processes[process.id] = process

    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        return self.definitions.get(definition_id)

    async def save_definition(self, definition: ProcessDefinition) -> None:
        self.definitions[definition.id] = definition


@dataclass
class MockEngine:
    """Mock WorkflowEngine for testing."""

    store: MockStore
    created_processes: list[ProcessInstance] = field(default_factory=list)
    started_processes: list[str] = field(default_factory=list)

    async def create_process(
        self,
        definition: ProcessDefinition,
        properties: dict[str, Any] | None = None,
    ) -> ProcessInstance:
        process = ProcessInstance(
            id=f"proc_{len(self.created_processes)}",
            definition_id=definition.id,
            state=ProcessState.CREATED,
            properties=properties or {},
        )
        self.created_processes.append(process)
        self.store.processes[process.id] = process
        return process

    async def start_process(self, process_id: str) -> None:
        self.started_processes.append(process_id)
        if process_id in self.store.processes:
            self.store.processes[process_id].state = ProcessState.RUNNING

    async def get_process_status(self, process_id: str) -> dict:
        process = self.store.processes.get(process_id)
        if process:
            return {"process": {"state": process.state.value}}
        return {"process": {"state": "not_found"}}


@pytest.fixture
def mock_store():
    """Create a mock store."""
    return MockStore()


@pytest.fixture
def mock_engine(mock_store):
    """Create a mock engine."""
    return MockEngine(store=mock_store)


@pytest.fixture
def simple_workflow_definition():
    """Create a simple workflow definition for testing."""
    return ProcessDefinition(
        id="test_workflow",
        name="Test Workflow",
        first_task_id="task1",
        tasks={
            "task1": TaskDefinition(
                id="task1",
                name="Task 1",
                action="test_action",
            ),
        },
        routings=[],
    )


@pytest.fixture
def mock_process(simple_workflow_definition):
    """Create a mock process instance."""
    return ProcessInstance(
        id="test_process",
        definition_id=simple_workflow_definition.id,
        state=ProcessState.RUNNING,
        properties={},
    )


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    return TaskInstance(
        id="test_task",
        process_id="test_process",
        task_definition_id="task1",
        state=TaskState.RUNNING,
        foe_id="foe_1",
        properties={},
    )


@pytest.fixture
def mock_task_definition():
    """Create a mock task definition."""
    return TaskDefinition(
        id="task1",
        name="Task 1",
        action="test_action",
    )


@pytest.fixture
def mock_context(mock_engine, mock_store, mock_process, mock_task_definition):
    """Create a mock execution context."""
    return ExecutionContext(
        engine=mock_engine,
        store=mock_store,
        process=mock_process,
        process_definition=ProcessDefinition(
            id="test_def",
            name="Test",
            first_task_id="task1",
            tasks={"task1": mock_task_definition},
            routings=[],
        ),
        task_definition=mock_task_definition,
        extras={},  # For engine-level dependency injection
    )

"""In-memory storage implementation for testing and ephemeral workflows."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskInstance,
    TaskState,
)
from zebra.storage.base import StateStore


class InMemoryStore(StateStore):
    """In-memory implementation of StateStore for testing.

    All data is lost when the process terminates. Useful for:
    - Unit testing
    - Development
    - Single-session workflows that don't need persistence
    """

    def __init__(self) -> None:
        self._definitions: dict[str, ProcessDefinition] = {}
        self._processes: dict[str, ProcessInstance] = {}
        self._tasks: dict[str, TaskInstance] = {}
        self._foes: dict[str, FlowOfExecution] = {}
        self._locks: dict[str, str] = {}  # process_id -> owner
        self._lock_events: dict[str, asyncio.Event] = {}

    # =========================================================================
    # Process Definition Operations
    # =========================================================================

    async def save_definition(self, definition: ProcessDefinition) -> None:
        self._definitions[definition.id] = definition

    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        return self._definitions.get(definition_id)

    async def list_definitions(self) -> list[ProcessDefinition]:
        return list(self._definitions.values())

    async def delete_definition(self, definition_id: str) -> bool:
        if definition_id in self._definitions:
            del self._definitions[definition_id]
            return True
        return False

    # =========================================================================
    # Process Instance Operations
    # =========================================================================

    async def save_process(self, process: ProcessInstance) -> None:
        self._processes[process.id] = process

    async def load_process(self, process_id: str) -> ProcessInstance | None:
        return self._processes.get(process_id)

    async def list_processes(
        self, definition_id: str | None = None, include_completed: bool = False
    ) -> list[ProcessInstance]:
        processes = list(self._processes.values())
        if definition_id:
            processes = [p for p in processes if p.definition_id == definition_id]
        if not include_completed:
            terminal_states = {ProcessState.COMPLETE, ProcessState.FAILED}
            processes = [p for p in processes if p.state not in terminal_states]
        return processes

    async def delete_process(self, process_id: str) -> bool:
        if process_id not in self._processes:
            return False
        del self._processes[process_id]
        # Clean up related tasks and FOEs
        self._tasks = {k: v for k, v in self._tasks.items() if v.process_id != process_id}
        self._foes = {k: v for k, v in self._foes.items() if v.process_id != process_id}
        return True

    async def get_running_processes(self) -> list[ProcessInstance]:
        """Get all processes in RUNNING state (excluding PAUSED)."""
        return [p for p in self._processes.values() if p.state == ProcessState.RUNNING]

    # =========================================================================
    # Task Instance Operations
    # =========================================================================

    async def save_task(self, task: TaskInstance) -> None:
        self._tasks[task.id] = task

    async def load_task(self, task_id: str) -> TaskInstance | None:
        return self._tasks.get(task_id)

    async def load_tasks_for_process(self, process_id: str) -> list[TaskInstance]:
        return [t for t in self._tasks.values() if t.process_id == process_id]

    async def delete_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    async def get_running_tasks(self, process_id: str | None = None) -> list[TaskInstance]:
        """Get all tasks in RUNNING state, optionally filtered by process_id."""
        tasks = self._tasks.values()
        if process_id:
            tasks = [t for t in tasks if t.process_id == process_id]
        return [t for t in tasks if t.state == TaskState.RUNNING]

    # =========================================================================
    # Flow of Execution Operations
    # =========================================================================

    async def save_foe(self, foe: FlowOfExecution) -> None:
        self._foes[foe.id] = foe

    async def load_foe(self, foe_id: str) -> FlowOfExecution | None:
        return self._foes.get(foe_id)

    async def load_foes_for_process(self, process_id: str) -> list[FlowOfExecution]:
        return [f for f in self._foes.values() if f.process_id == process_id]

    async def delete_foe(self, foe_id: str) -> bool:
        """Delete a flow of execution. Returns True if deleted."""
        if foe_id in self._foes:
            del self._foes[foe_id]
            return True
        return False

    # =========================================================================
    # Locking Operations
    # =========================================================================

    async def acquire_lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> bool:
        """Acquire a lock on a process. Uses asyncio.Event for waiting."""
        deadline = asyncio.get_event_loop().time() + timeout_seconds

        while True:
            # Try to acquire
            if process_id not in self._locks:
                self._locks[process_id] = owner
                return True

            # Already owned by us
            if self._locks.get(process_id) == owner:
                return True

            # Check timeout
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return False

            # Wait for lock release
            if process_id not in self._lock_events:
                self._lock_events[process_id] = asyncio.Event()

            try:
                await asyncio.wait_for(
                    self._lock_events[process_id].wait(),
                    timeout=min(remaining, 1.0),
                )
                self._lock_events[process_id].clear()
            except TimeoutError:
                continue

    async def release_lock(self, process_id: str, owner: str) -> bool:
        """Release a lock on a process."""
        if self._locks.get(process_id) != owner:
            return False

        del self._locks[process_id]

        # Notify waiters
        if process_id in self._lock_events:
            self._lock_events[process_id].set()

        return True

    # =========================================================================
    # Transaction Support
    # =========================================================================

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """In-memory store doesn't need transactions, but we implement for API compatibility."""
        yield

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def clear(self) -> None:
        """Clear all data. Useful for testing."""
        self._definitions.clear()
        self._processes.clear()
        self._tasks.clear()
        self._foes.clear()
        self._locks.clear()
        self._lock_events.clear()

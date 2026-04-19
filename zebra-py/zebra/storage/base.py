"""Abstract base class for workflow state storage.

This module defines the StateStore interface that all storage implementations
must follow. Corresponds to Java IStateFactory.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskInstance,
)


class StateStore(ABC):
    """Abstract base class for workflow state persistence.

    Implementations must provide atomic operations for saving and loading
    workflow state, as well as locking mechanisms for concurrent access.

    Corresponds to Java IStateFactory interface.
    """

    # =========================================================================
    # Process Definition Operations
    # =========================================================================

    @abstractmethod
    async def save_definition(self, definition: ProcessDefinition) -> None:
        """Save or update a process definition."""
        pass

    @abstractmethod
    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        """Load a process definition by ID. Returns None if not found."""
        pass

    @abstractmethod
    async def list_definitions(self) -> list[ProcessDefinition]:
        """List all available process definitions."""
        pass

    @abstractmethod
    async def delete_definition(self, definition_id: str) -> bool:
        """Delete a process definition. Returns True if deleted, False if not found."""
        pass

    # =========================================================================
    # Process Instance Operations
    # =========================================================================

    @abstractmethod
    async def save_process(self, process: ProcessInstance) -> None:
        """Save or update a process instance."""
        pass

    @abstractmethod
    async def load_process(self, process_id: str) -> ProcessInstance | None:
        """Load a process instance by ID. Returns None if not found."""
        pass

    @abstractmethod
    async def list_processes(
        self, definition_id: str | None = None, include_completed: bool = False
    ) -> list[ProcessInstance]:
        """List process instances, optionally filtered by definition and completion status."""
        pass

    @abstractmethod
    async def delete_process(self, process_id: str) -> bool:
        """Delete a process instance and all related data. Returns True if deleted."""
        pass

    @abstractmethod
    async def get_running_processes(self) -> list[ProcessInstance]:
        """Get all processes that are in RUNNING state (excluding PAUSED)."""
        pass

    async def get_processes_by_state(
        self,
        state: ProcessState,
        exclude_children: bool = False,
    ) -> list[ProcessInstance]:
        """Get processes in a specific state, ordered by created_at ascending.

        Args:
            state: The ``ProcessState`` to filter on.
            exclude_children: If True, only return top-level processes
                (``parent_process_id IS NULL``).

        Returns:
            List of matching ``ProcessInstance`` objects.

        The default implementation calls ``list_processes`` and filters
        in memory. Backends should override for efficiency.
        """
        from zebra.core.models import ProcessState as PS

        processes = await self.list_processes(include_completed=(state in (PS.COMPLETE, PS.FAILED)))
        results = [p for p in processes if p.state == state]
        if exclude_children:
            results = [p for p in results if p.parent_process_id is None]
        results.sort(key=lambda p: p.created_at)
        return results

    # =========================================================================
    # Task Instance Operations
    # =========================================================================

    @abstractmethod
    async def save_task(self, task: TaskInstance) -> None:
        """Save or update a task instance."""
        pass

    @abstractmethod
    async def load_task(self, task_id: str) -> TaskInstance | None:
        """Load a task instance by ID. Returns None if not found."""
        pass

    @abstractmethod
    async def load_tasks_for_process(self, process_id: str) -> list[TaskInstance]:
        """Load all task instances for a process."""
        pass

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """Delete a task instance. Returns True if deleted."""
        pass

    @abstractmethod
    async def get_running_tasks(self, process_id: str | None = None) -> list[TaskInstance]:
        """Get all tasks in RUNNING state, optionally filtered by process_id."""
        pass

    async def get_ready_tasks(self) -> list[TaskInstance]:
        """Get all tasks in READY state across all processes.

        The default implementation iterates all non-terminal processes and
        collects READY tasks. Backends should override for efficiency.
        """
        from zebra.core.models import TaskState as TS

        results: list[TaskInstance] = []
        processes = await self.list_processes(include_completed=False)
        for proc in processes:
            tasks = await self.load_tasks_for_process(proc.id)
            results.extend(t for t in tasks if t.state == TS.READY)
        results.sort(key=lambda t: t.created_at)
        return results

    # =========================================================================
    # Flow of Execution Operations
    # =========================================================================

    @abstractmethod
    async def save_foe(self, foe: FlowOfExecution) -> None:
        """Save or update a flow of execution."""
        pass

    @abstractmethod
    async def load_foe(self, foe_id: str) -> FlowOfExecution | None:
        """Load a flow of execution by ID. Returns None if not found."""
        pass

    @abstractmethod
    async def load_foes_for_process(self, process_id: str) -> list[FlowOfExecution]:
        """Load all FOEs for a process."""
        pass

    @abstractmethod
    async def delete_foe(self, foe_id: str) -> bool:
        """Delete a flow of execution. Returns True if deleted, False if not found."""
        pass

    # =========================================================================
    # Locking Operations
    # =========================================================================

    @abstractmethod
    async def acquire_lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> bool:
        """Acquire an exclusive lock on a process instance.

        Args:
            process_id: The process to lock
            owner: Identifier for the lock owner (e.g., engine instance ID)
            timeout_seconds: How long to wait for lock acquisition

        Returns:
            True if lock acquired, False if timeout
        """
        pass

    @abstractmethod
    async def release_lock(self, process_id: str, owner: str) -> bool:
        """Release a lock on a process instance.

        Args:
            process_id: The process to unlock
            owner: Must match the owner that acquired the lock

        Returns:
            True if released, False if not locked or wrong owner
        """
        pass

    @asynccontextmanager
    async def lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> AsyncIterator[bool]:
        """Context manager for acquiring and releasing a process lock.

        Usage:
            async with store.lock(process_id, owner) as acquired:
                if acquired:
                    # Do work with process
        """
        acquired = await self.acquire_lock(process_id, owner, timeout_seconds)
        try:
            yield acquired
        finally:
            if acquired:
                await self.release_lock(process_id, owner)

    # =========================================================================
    # Transaction Support (Optional)
    # =========================================================================

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Context manager for transactional operations.

        Default implementation is a no-op. Override in implementations
        that support transactions.
        """
        yield

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def initialize(self) -> None:
        """Initialize the store (create tables, etc.). Called once at startup."""
        pass

    async def close(self) -> None:
        """Close the store and release resources."""
        pass

"""Django ORM implementation of the Zebra StateStore interface.

This module provides a Django-based storage backend for the Zebra workflow engine,
handling all persistence through Django's ORM which transparently manages Oracle
CLOB fields and other database-specific concerns.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone as django_timezone
from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskInstance,
    TaskState,
)
from zebra.storage.base import StateStore

from .api.models import (
    FlowOfExecutionModel,
    ProcessDefinitionModel,
    ProcessInstanceModel,
    ProcessLockModel,
    TaskInstanceModel,
)

logger = logging.getLogger(__name__)


class DjangoStore(StateStore):
    """Django ORM implementation of the Zebra StateStore interface.

    Uses Django's ORM to handle database operations, which transparently
    manages Oracle CLOB fields via TextField.
    """

    def __init__(self):
        """Initialize the Django store."""
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store. Django handles schema via migrations."""
        self._initialized = True
        logger.info("DjangoStore initialized")

    async def close(self) -> None:
        """Close the store. Django manages connections automatically."""
        pass

    # =========================================================================
    # Process Definition Operations
    # =========================================================================

    async def save_definition(self, definition: ProcessDefinition) -> None:
        """Save or update a process definition."""

        @sync_to_async
        def _save():
            ProcessDefinitionModel.objects.update_or_create(
                id=definition.id,
                defaults={
                    "name": definition.name,
                    "version": definition.version,
                    "data": definition.model_dump_json(),
                },
            )

        await _save()

    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        """Load a process definition by ID."""

        @sync_to_async
        def _load():
            try:
                model = ProcessDefinitionModel.objects.get(id=definition_id)
                return ProcessDefinition.model_validate_json(model.data)
            except ProcessDefinitionModel.DoesNotExist:
                return None

        return await _load()

    async def list_definitions(self) -> list[ProcessDefinition]:
        """List all available process definitions."""

        @sync_to_async
        def _list():
            models = ProcessDefinitionModel.objects.all().order_by("-updated_at")
            return [ProcessDefinition.model_validate_json(m.data) for m in models]

        return await _list()

    async def delete_definition(self, definition_id: str) -> bool:
        """Delete a process definition."""

        @sync_to_async
        def _delete():
            deleted, _ = ProcessDefinitionModel.objects.filter(id=definition_id).delete()
            return deleted > 0

        return await _delete()

    # =========================================================================
    # Process Instance Operations
    # =========================================================================

    async def save_process(self, process: ProcessInstance) -> None:
        """Save or update a process instance."""

        @sync_to_async
        def _save():
            ProcessInstanceModel.objects.update_or_create(
                id=process.id,
                defaults={
                    "definition_id": process.definition_id,
                    "state": process.state.value,
                    "properties": json.dumps(process.properties),
                    "parent_process_id": process.parent_process_id,
                    "parent_task_id": process.parent_task_id,
                    "created_at": process.created_at,
                    "updated_at": process.updated_at,
                    "completed_at": process.completed_at,
                },
            )

        await _save()

    async def load_process(self, process_id: str) -> ProcessInstance | None:
        """Load a process instance by ID."""

        @sync_to_async
        def _load():
            try:
                model = ProcessInstanceModel.objects.get(id=process_id)
                return self._model_to_process(model)
            except ProcessInstanceModel.DoesNotExist:
                return None

        return await _load()

    async def list_processes(
        self, definition_id: str | None = None, include_completed: bool = False
    ) -> list[ProcessInstance]:
        """List process instances."""

        @sync_to_async
        def _list():
            queryset = ProcessInstanceModel.objects.all()

            if definition_id:
                queryset = queryset.filter(definition_id=definition_id)

            if not include_completed:
                queryset = queryset.exclude(
                    state__in=[ProcessState.COMPLETE.value, ProcessState.FAILED.value]
                )

            queryset = queryset.order_by("-created_at")
            return [self._model_to_process(m) for m in queryset]

        return await _list()

    async def delete_process(self, process_id: str) -> bool:
        """Delete a process instance and all related data."""

        @sync_to_async
        def _delete():
            with transaction.atomic():
                # Delete related tasks and FOEs first
                TaskInstanceModel.objects.filter(process_id=process_id).delete()
                FlowOfExecutionModel.objects.filter(process_id=process_id).delete()
                ProcessLockModel.objects.filter(process_id=process_id).delete()
                deleted, _ = ProcessInstanceModel.objects.filter(id=process_id).delete()
                return deleted > 0

        return await _delete()

    async def get_running_processes(self) -> list[ProcessInstance]:
        """Get all processes in RUNNING state."""

        @sync_to_async
        def _get():
            models = ProcessInstanceModel.objects.filter(state=ProcessState.RUNNING.value).order_by(
                "-created_at"
            )
            return [self._model_to_process(m) for m in models]

        return await _get()

    def _model_to_process(self, model: ProcessInstanceModel) -> ProcessInstance:
        """Convert Django model to ProcessInstance."""
        properties = json.loads(model.properties) if model.properties else {}
        return ProcessInstance(
            id=model.id,
            definition_id=model.definition_id,
            state=ProcessState(model.state),
            properties=properties,
            parent_process_id=model.parent_process_id,
            parent_task_id=model.parent_task_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
        )

    # =========================================================================
    # Task Instance Operations
    # =========================================================================

    async def save_task(self, task: TaskInstance) -> None:
        """Save or update a task instance."""

        @sync_to_async
        def _save():
            result_json = json.dumps(task.result) if task.result is not None else None

            TaskInstanceModel.objects.update_or_create(
                id=task.id,
                defaults={
                    "process_id": task.process_id,
                    "task_definition_id": task.task_definition_id,
                    "state": task.state.value,
                    "foe_id": task.foe_id,
                    "properties": json.dumps(task.properties),
                    "result": result_json,
                    "error": task.error,
                    "execution_attempt": task.execution_attempt,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "completed_at": task.completed_at,
                },
            )

        await _save()

    async def load_task(self, task_id: str) -> TaskInstance | None:
        """Load a task instance by ID."""

        @sync_to_async
        def _load():
            try:
                model = TaskInstanceModel.objects.get(id=task_id)
                return self._model_to_task(model)
            except TaskInstanceModel.DoesNotExist:
                return None

        return await _load()

    async def load_tasks_for_process(self, process_id: str) -> list[TaskInstance]:
        """Load all task instances for a process."""

        @sync_to_async
        def _load():
            models = TaskInstanceModel.objects.filter(process_id=process_id).order_by("created_at")
            return [self._model_to_task(m) for m in models]

        return await _load()

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task instance."""

        @sync_to_async
        def _delete():
            deleted, _ = TaskInstanceModel.objects.filter(id=task_id).delete()
            return deleted > 0

        return await _delete()

    async def get_running_tasks(self, process_id: str | None = None) -> list[TaskInstance]:
        """Get all tasks in RUNNING state."""

        @sync_to_async
        def _get():
            queryset = TaskInstanceModel.objects.filter(state=TaskState.RUNNING.value)
            if process_id:
                queryset = queryset.filter(process_id=process_id)
            queryset = queryset.order_by("created_at")
            return [self._model_to_task(m) for m in queryset]

        return await _get()

    def _model_to_task(self, model: TaskInstanceModel) -> TaskInstance:
        """Convert Django model to TaskInstance."""
        properties = json.loads(model.properties) if model.properties else {}
        result = json.loads(model.result) if model.result else None

        return TaskInstance(
            id=model.id,
            process_id=model.process_id,
            task_definition_id=model.task_definition_id,
            state=TaskState(model.state),
            foe_id=model.foe_id,
            properties=properties,
            result=result,
            error=model.error,
            execution_attempt=model.execution_attempt,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
        )

    # =========================================================================
    # Flow of Execution Operations
    # =========================================================================

    async def save_foe(self, foe: FlowOfExecution) -> None:
        """Save or update a flow of execution."""

        @sync_to_async
        def _save():
            FlowOfExecutionModel.objects.update_or_create(
                id=foe.id,
                defaults={
                    "process_id": foe.process_id,
                    "parent_foe_id": foe.parent_foe_id,
                    "created_at": foe.created_at,
                },
            )

        await _save()

    async def load_foe(self, foe_id: str) -> FlowOfExecution | None:
        """Load a flow of execution by ID."""

        @sync_to_async
        def _load():
            try:
                model = FlowOfExecutionModel.objects.get(id=foe_id)
                return self._model_to_foe(model)
            except FlowOfExecutionModel.DoesNotExist:
                return None

        return await _load()

    async def load_foes_for_process(self, process_id: str) -> list[FlowOfExecution]:
        """Load all FOEs for a process."""

        @sync_to_async
        def _load():
            models = FlowOfExecutionModel.objects.filter(process_id=process_id).order_by(
                "created_at"
            )
            return [self._model_to_foe(m) for m in models]

        return await _load()

    async def delete_foe(self, foe_id: str) -> bool:
        """Delete a flow of execution."""

        @sync_to_async
        def _delete():
            deleted, _ = FlowOfExecutionModel.objects.filter(id=foe_id).delete()
            return deleted > 0

        return await _delete()

    def _model_to_foe(self, model: FlowOfExecutionModel) -> FlowOfExecution:
        """Convert Django model to FlowOfExecution."""
        return FlowOfExecution(
            id=model.id,
            process_id=model.process_id,
            parent_foe_id=model.parent_foe_id,
            created_at=model.created_at,
        )

    # =========================================================================
    # Locking Operations
    # =========================================================================

    async def acquire_lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> bool:
        """Acquire an exclusive lock on a process instance."""

        @sync_to_async
        def _acquire():
            now = django_timezone.now()
            expires_at = now + timedelta(seconds=timeout_seconds)

            with transaction.atomic():
                # Try to delete any expired locks
                ProcessLockModel.objects.filter(process_id=process_id, expires_at__lt=now).delete()

                # Try to get existing lock
                try:
                    existing = ProcessLockModel.objects.select_for_update(nowait=True).get(
                        process_id=process_id
                    )

                    # Lock exists and not expired - check if we own it
                    if existing.owner == owner:
                        # Extend our own lock
                        existing.expires_at = expires_at
                        existing.save()
                        return True
                    else:
                        # Someone else has the lock
                        return False

                except ProcessLockModel.DoesNotExist:
                    # No lock exists, create one
                    ProcessLockModel.objects.create(
                        process_id=process_id,
                        owner=owner,
                        expires_at=expires_at,
                    )
                    return True

        try:
            return await _acquire()
        except Exception as e:
            logger.warning(f"Failed to acquire lock for {process_id}: {e}")
            return False

    async def release_lock(self, process_id: str, owner: str) -> bool:
        """Release a lock on a process instance."""

        @sync_to_async
        def _release():
            deleted, _ = ProcessLockModel.objects.filter(
                process_id=process_id, owner=owner
            ).delete()
            return deleted > 0

        return await _release()

    @asynccontextmanager
    async def lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> AsyncIterator[bool]:
        """Context manager for acquiring and releasing a process lock."""
        acquired = await self.acquire_lock(process_id, owner, timeout_seconds)
        try:
            yield acquired
        finally:
            if acquired:
                await self.release_lock(process_id, owner)

    # =========================================================================
    # Transaction Support
    # =========================================================================

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Context manager for transactional operations."""

        # Django's transaction.atomic() is synchronous, wrap it
        @sync_to_async
        def _begin():
            return transaction.atomic().__enter__()

        @sync_to_async
        def _commit(atomic):
            atomic.__exit__(None, None, None)

        @sync_to_async
        def _rollback(atomic, exc_type, exc_val, exc_tb):
            atomic.__exit__(exc_type, exc_val, exc_tb)

        atomic = await _begin()
        try:
            yield
            await _commit(atomic)
        except Exception as e:
            await _rollback(atomic, type(e), e, e.__traceback__)
            raise

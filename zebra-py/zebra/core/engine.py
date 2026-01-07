"""Core workflow engine implementation.

This module contains the WorkflowEngine class that controls the execution
of workflow processes. Ported from Java Engine class.
"""

import logging
import uuid
from datetime import datetime, timezone

from zebra.core.exceptions import (
    ActionNotFoundError,
    DefinitionNotFoundError,
    ExecutionError,
    InvalidStateTransitionError,
    LockError,
    ProcessNotFoundError,
    RoutingError,
    TaskExecutionError,
    TaskNotFoundError,
)
from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.core.sync import TaskSync
from zebra.storage.base import StateStore
from zebra.tasks.base import ExecutionContext
from zebra.tasks.registry import ActionRegistry

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Main workflow engine that controls process execution.

    Corresponds to Java Engine class. Handles:
    - Process creation and lifecycle
    - Task state transitions
    - Routing evaluation (serial and parallel)
    - Synchronization/join points
    - Action execution

    Example:
        store = SQLiteStore("workflows.db")
        await store.initialize()

        registry = ActionRegistry()
        registry.register_defaults()

        engine = WorkflowEngine(store, registry)

        # Create and start a process
        process = await engine.create_process(my_definition)
        await engine.start_process(process.id)
    """

    def __init__(
        self,
        store: StateStore,
        action_registry: ActionRegistry,
        engine_id: str | None = None,
    ) -> None:
        """Initialize the workflow engine.

        Args:
            store: Storage backend for persistence
            action_registry: Registry of task actions and conditions
            engine_id: Optional unique ID for this engine instance (for locking)
        """
        self.store = store
        self.actions = action_registry
        self.engine_id = engine_id or str(uuid.uuid4())
        self._task_sync = TaskSync()

    # =========================================================================
    # Process Lifecycle
    # =========================================================================

    async def create_process(
        self,
        definition: ProcessDefinition,
        properties: dict | None = None,
        parent_process_id: str | None = None,
        parent_task_id: str | None = None,
    ) -> ProcessInstance:
        """Create a new process instance from a definition.

        The process is created in CREATED state and must be started
        with start_process() to begin execution.

        Args:
            definition: The process definition to instantiate
            properties: Optional initial properties for the process
            parent_process_id: ID of parent process (for subflows)
            parent_task_id: ID of parent task (for subflows)

        Returns:
            The newly created ProcessInstance
        """
        # Ensure definition is saved
        await self.store.save_definition(definition)

        process = ProcessInstance(
            id=str(uuid.uuid4()),
            definition_id=definition.id,
            state=ProcessState.CREATED,
            properties=properties or {},
            parent_process_id=parent_process_id,
            parent_task_id=parent_task_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await self.store.save_process(process)
        logger.info(f"Created process {process.id} from definition {definition.id}")
        return process

    async def start_process(self, process_id: str) -> ProcessInstance:
        """Start a process that is in CREATED state.

        Creates the first task and begins execution. If the first task
        is auto-executable, it will be transitioned immediately.

        Args:
            process_id: ID of the process to start

        Returns:
            The updated ProcessInstance

        Raises:
            ProcessNotFoundError: If process doesn't exist
            InvalidStateTransitionError: If process is not in CREATED state
        """
        process = await self._load_process(process_id)

        if process.state != ProcessState.CREATED:
            raise InvalidStateTransitionError(
                f"Process {process_id} is in state {process.state}, expected CREATED"
            )

        definition = await self._load_definition(process.definition_id)

        # Run process construct action if defined
        if definition.construct_action:
            await self._run_process_construct(process, definition)

        # Update state to RUNNING
        process = process.model_copy(
            update={"state": ProcessState.RUNNING, "updated_at": datetime.now(timezone.utc)}
        )
        await self.store.save_process(process)

        # Create the first FOE and task
        foe = await self._create_foe(process)
        first_task_def = definition.get_task(definition.first_task_id)
        task = await self._create_task(first_task_def, process, foe)

        logger.info(f"Started process {process_id}, first task is {task.id}")

        # If first task is auto, transition it
        if first_task_def.auto:
            await self.transition_task(task.id)

        return await self._load_process(process_id)

    async def pause_process(self, process_id: str) -> ProcessInstance:
        """Pause a running process.

        The process can be resumed later with resume_process().

        Args:
            process_id: ID of the process to pause

        Returns:
            The updated ProcessInstance
        """
        process = await self._load_process(process_id)

        if process.state != ProcessState.RUNNING:
            raise InvalidStateTransitionError(
                f"Process {process_id} is in state {process.state}, expected RUNNING"
            )

        process = process.model_copy(
            update={"state": ProcessState.PAUSED, "updated_at": datetime.now(timezone.utc)}
        )
        await self.store.save_process(process)
        logger.info(f"Paused process {process_id}")
        return process

    async def resume_process(self, process_id: str) -> ProcessInstance:
        """Resume a paused process.

        Args:
            process_id: ID of the process to resume

        Returns:
            The updated ProcessInstance
        """
        process = await self._load_process(process_id)

        if process.state != ProcessState.PAUSED:
            raise InvalidStateTransitionError(
                f"Process {process_id} is in state {process.state}, expected PAUSED"
            )

        process = process.model_copy(
            update={"state": ProcessState.RUNNING, "updated_at": datetime.now(timezone.utc)}
        )
        await self.store.save_process(process)
        logger.info(f"Resumed process {process_id}")

        # Check if there are any auto tasks that need to run
        await self._process_pending_auto_tasks(process)

        return process

    # =========================================================================
    # Task Transitions
    # =========================================================================

    async def transition_task(self, task_id: str) -> list[TaskInstance]:
        """Transition a task through its lifecycle.

        This is the main entry point for task execution. It handles:
        - Acquiring a lock on the process
        - Running the task action (if any)
        - Evaluating outbound routings
        - Creating new tasks based on routing results
        - Processing auto tasks recursively

        Args:
            task_id: ID of the task to transition

        Returns:
            List of new TaskInstances created as a result of routing

        Raises:
            TaskNotFoundError: If task doesn't exist
            LockError: If unable to acquire process lock
        """
        task = await self._load_task(task_id)
        process = await self._load_process(task.process_id)

        # Acquire lock on process
        async with self.store.lock(process.id, self.engine_id) as acquired:
            if not acquired:
                raise LockError(f"Failed to acquire lock on process {process.id}")

            # Stack-based processing for auto tasks
            task_stack: list[TaskInstance] = [task]
            all_created_tasks: list[TaskInstance] = []

            while task_stack:
                current_task = task_stack.pop()

                try:
                    created_tasks = await self._transition_task_internal(current_task, process)
                    all_created_tasks.extend(created_tasks)

                    # Add auto tasks to stack for processing
                    definition = await self._load_definition(process.definition_id)
                    for new_task in created_tasks:
                        task_def = definition.get_task(new_task.task_definition_id)
                        if task_def.auto or task_def.synchronized:
                            if new_task not in task_stack:
                                task_stack.append(new_task)

                except Exception as e:
                    logger.error(f"Error transitioning task {current_task.id}: {e}")
                    raise

            # Check if process is complete
            process = await self._load_process(process.id)
            tasks = await self.store.load_tasks_for_process(process.id)
            active_tasks = [t for t in tasks if t.state not in {TaskState.COMPLETE, TaskState.FAILED}]

            if not active_tasks:
                await self._complete_process(process)

        return all_created_tasks

    async def complete_task(
        self, task_id: str, result: TaskResult | None = None
    ) -> list[TaskInstance]:
        """Complete a manual task and transition it.

        Use this for tasks that are not auto-executable (e.g., waiting
        for user input).

        Args:
            task_id: ID of the task to complete
            result: Optional result from the task

        Returns:
            List of new TaskInstances created as a result of routing
        """
        task = await self._load_task(task_id)

        if task.state not in {TaskState.READY, TaskState.RUNNING}:
            raise InvalidStateTransitionError(
                f"Task {task_id} is in state {task.state}, expected READY or RUNNING"
            )

        # Update task with result
        task = task.model_copy(
            update={
                "state": TaskState.COMPLETE,
                "result": result.output if result else None,
                "error": result.error if result and not result.success else None,
                "updated_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
            }
        )

        if result and not result.success:
            task = task.model_copy(update={"state": TaskState.FAILED})

        await self.store.save_task(task)

        # Store result in process properties for later reference
        process = await self._load_process(task.process_id)
        if result and result.output is not None:
            process.properties[f"__task_output_{task.task_definition_id}"] = result.output
            process = process.model_copy(update={"updated_at": datetime.now(timezone.utc)})
            await self.store.save_process(process)

        return await self.transition_task(task_id)

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _transition_task_internal(
        self, task: TaskInstance, process: ProcessInstance
    ) -> list[TaskInstance]:
        """Internal task transition logic.

        Args:
            task: The task to transition
            process: The owning process

        Returns:
            List of newly created task instances
        """
        definition = await self._load_definition(process.definition_id)
        task_def = definition.get_task(task.task_definition_id)

        # Handle sync tasks
        if task_def.synchronized and task.state == TaskState.AWAITING_SYNC:
            active_tasks = await self.store.load_tasks_for_process(process.id)
            if self._task_sync.is_task_blocked(task, task_def, process, definition, active_tasks):
                logger.info(f"Task {task.id} is blocked, waiting for sync")
                return []

            # Unblocked - transition to READY
            task = task.model_copy(
                update={"state": TaskState.READY, "updated_at": datetime.now(timezone.utc)}
            )
            await self.store.save_task(task)

        # Run task if in READY state
        if task.state == TaskState.READY:
            await self._run_task(task, task_def, process, definition)
            task = await self._load_task(task.id)  # Reload after run

        # Check if task completed
        if task.state != TaskState.COMPLETE:
            logger.info(f"Task {task.id} is in state {task.state}, not transitioning further")
            return []

        # Run routing
        created_tasks = await self._run_routing(task, task_def, process, definition)

        # Check for sync tasks that might now be unblocked
        active_tasks = await self.store.load_tasks_for_process(process.id)
        sync_task_ids = self._task_sync.get_potential_task_locks(task_def, definition)

        for active_task in active_tasks:
            if active_task.task_definition_id in sync_task_ids:
                if active_task.state == TaskState.AWAITING_SYNC:
                    if active_task not in created_tasks:
                        created_tasks.append(active_task)

        # Delete completed task
        await self.store.delete_task(task.id)

        return created_tasks

    async def _run_task(
        self,
        task: TaskInstance,
        task_def: TaskDefinition,
        process: ProcessInstance,
        definition: ProcessDefinition,
    ) -> None:
        """Execute a task's action."""
        # Update state to RUNNING
        task = task.model_copy(
            update={"state": TaskState.RUNNING, "updated_at": datetime.now(timezone.utc)}
        )
        await self.store.save_task(task)

        context = ExecutionContext(
            engine=self,
            store=self.store,
            process=process,
            process_definition=definition,
            task_definition=task_def,
        )

        result: TaskResult

        if task_def.action:
            try:
                action = self.actions.get_action(task_def.action)

                # Run construct if defined
                await action.on_construct(task, context)

                # Run main action
                result = await action.run(task, context)

                # Run destruct
                await action.on_destruct(task, context)

            except ActionNotFoundError:
                result = TaskResult.fail(f"Action '{task_def.action}' not found")
            except Exception as e:
                logger.exception(f"Error running task {task.id}")
                result = TaskResult.fail(str(e))
        else:
            # No action - auto-complete
            result = TaskResult.ok()

        # Update task with result
        new_state = TaskState.COMPLETE if result.success else TaskState.FAILED
        task = task.model_copy(
            update={
                "state": new_state,
                "result": result.output,
                "error": result.error,
                "updated_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
            }
        )
        await self.store.save_task(task)

        # Store result in process properties
        if result.output is not None:
            process.properties[f"__task_output_{task_def.id}"] = result.output
            process = process.model_copy(update={"updated_at": datetime.now(timezone.utc)})
            await self.store.save_process(process)

    async def _run_routing(
        self,
        task: TaskInstance,
        task_def: TaskDefinition,
        process: ProcessInstance,
        definition: ProcessDefinition,
    ) -> list[TaskInstance]:
        """Evaluate and execute outbound routings."""
        routings = definition.get_routings_from(task_def.id)
        if not routings:
            return []

        context = ExecutionContext(
            engine=self,
            store=self.store,
            process=process,
            process_definition=definition,
            task_definition=task_def,
        )

        done_serial_routing = False
        create_list: list[RoutingDefinition] = []

        for routing in routings:
            do_routing = False

            if not routing.parallel and not done_serial_routing:
                do_routing = True
            elif routing.parallel:
                do_routing = True

            if do_routing:
                # Evaluate condition
                try:
                    condition = self.actions.get_condition(routing.condition)
                    should_fire = await condition.evaluate(routing, task, context)
                except ActionNotFoundError:
                    logger.warning(f"Condition '{routing.condition}' not found, defaulting to True")
                    should_fire = True
                except Exception as e:
                    logger.error(f"Error evaluating condition: {e}")
                    should_fire = False

                if should_fire:
                    create_list.append(routing)
                    if not routing.parallel:
                        done_serial_routing = True

        # Check for routing errors
        if not create_list and routings:
            task = task.model_copy(update={"state": TaskState.FAILED, "error": "No routing fired"})
            await self.store.save_task(task)
            raise RoutingError(f"Routing exists for task {task.id} but none fired")

        # Create new tasks
        created_tasks: list[TaskInstance] = []
        foe_serial: FlowOfExecution | None = None

        for routing in create_list:
            dest_task_def = definition.get_task(routing.dest_task_id)

            if routing.parallel:
                foe = await self._create_foe(process, task.foe_id)
            elif foe_serial is None:
                foe = await self.store.load_foe(task.foe_id)
                if foe is None:
                    foe = await self._create_foe(process, task.foe_id)
                foe_serial = foe
            else:
                foe = foe_serial

            new_task = await self._create_task(dest_task_def, process, foe)
            if new_task.id not in [t.id for t in created_tasks]:
                created_tasks.append(new_task)

        return created_tasks

    async def _create_task(
        self,
        task_def: TaskDefinition,
        process: ProcessInstance,
        foe: FlowOfExecution,
    ) -> TaskInstance:
        """Create a new task instance."""
        # For sync tasks, check if one already exists
        if task_def.synchronized:
            existing_tasks = await self.store.load_tasks_for_process(process.id)
            for existing in existing_tasks:
                if existing.task_definition_id == task_def.id:
                    logger.info(f"Reusing existing sync task {existing.id}")
                    return existing

            # New sync task gets new FOE
            foe = await self._create_foe(process, foe.id)

        # Determine initial state
        if task_def.synchronized:
            initial_state = TaskState.AWAITING_SYNC
        elif task_def.construct_action:
            initial_state = TaskState.PENDING
        else:
            initial_state = TaskState.READY

        task = TaskInstance(
            id=str(uuid.uuid4()),
            process_id=process.id,
            task_definition_id=task_def.id,
            state=initial_state,
            foe_id=foe.id,
            properties=dict(task_def.properties),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        await self.store.save_task(task)
        logger.info(f"Created task {task.id} ({task_def.name}) in state {initial_state}")
        return task

    async def _create_foe(
        self, process: ProcessInstance, parent_foe_id: str | None = None
    ) -> FlowOfExecution:
        """Create a new Flow of Execution."""
        foe = FlowOfExecution(
            id=str(uuid.uuid4()),
            process_id=process.id,
            parent_foe_id=parent_foe_id,
            created_at=datetime.now(timezone.utc),
        )
        await self.store.save_foe(foe)
        return foe

    async def _complete_process(self, process: ProcessInstance) -> None:
        """Mark a process as complete."""
        definition = await self._load_definition(process.definition_id)

        # Run destruct action if defined
        if definition.destruct_action:
            await self._run_process_destruct(process, definition)

        process = process.model_copy(
            update={
                "state": ProcessState.COMPLETE,
                "updated_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
            }
        )
        await self.store.save_process(process)
        logger.info(f"Process {process.id} completed")

    async def _run_process_construct(
        self, process: ProcessInstance, definition: ProcessDefinition
    ) -> None:
        """Run the process construct action."""
        if not definition.construct_action:
            return

        try:
            action = self.actions.get_action(definition.construct_action)
            # Create a dummy task instance for the construct action
            task = TaskInstance(
                id=str(uuid.uuid4()),
                process_id=process.id,
                task_definition_id="__process_construct__",
                state=TaskState.RUNNING,
                foe_id="__process_construct__",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            context = ExecutionContext(
                engine=self,
                store=self.store,
                process=process,
                process_definition=definition,
                task_definition=TaskDefinition(id="__process_construct__", name="Process Construct"),
            )
            await action.run(task, context)
        except Exception as e:
            logger.error(f"Error running process construct: {e}")
            raise ExecutionError(f"Process construct failed: {e}")

    async def _run_process_destruct(
        self, process: ProcessInstance, definition: ProcessDefinition
    ) -> None:
        """Run the process destruct action."""
        if not definition.destruct_action:
            return

        try:
            action = self.actions.get_action(definition.destruct_action)
            task = TaskInstance(
                id=str(uuid.uuid4()),
                process_id=process.id,
                task_definition_id="__process_destruct__",
                state=TaskState.RUNNING,
                foe_id="__process_destruct__",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            context = ExecutionContext(
                engine=self,
                store=self.store,
                process=process,
                process_definition=definition,
                task_definition=TaskDefinition(id="__process_destruct__", name="Process Destruct"),
            )
            await action.run(task, context)
        except Exception as e:
            logger.error(f"Error running process destruct: {e}")
            # Don't raise - process completion should still happen

    async def _process_pending_auto_tasks(self, process: ProcessInstance) -> None:
        """Process any pending auto tasks after resume."""
        tasks = await self.store.load_tasks_for_process(process.id)
        definition = await self._load_definition(process.definition_id)

        for task in tasks:
            if task.state == TaskState.READY:
                task_def = definition.get_task(task.task_definition_id)
                if task_def.auto:
                    await self.transition_task(task.id)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _load_process(self, process_id: str) -> ProcessInstance:
        """Load a process instance, raising if not found."""
        process = await self.store.load_process(process_id)
        if process is None:
            raise ProcessNotFoundError(f"Process {process_id} not found")
        return process

    async def _load_task(self, task_id: str) -> TaskInstance:
        """Load a task instance, raising if not found."""
        task = await self.store.load_task(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task

    async def _load_definition(self, definition_id: str) -> ProcessDefinition:
        """Load a process definition, raising if not found."""
        definition = await self.store.load_definition(definition_id)
        if definition is None:
            raise DefinitionNotFoundError(f"Definition {definition_id} not found")
        return definition

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_process_status(self, process_id: str) -> dict:
        """Get detailed status of a process."""
        process = await self._load_process(process_id)
        tasks = await self.store.load_tasks_for_process(process_id)
        definition = await self._load_definition(process.definition_id)

        return {
            "process": {
                "id": process.id,
                "definition": definition.name,
                "state": process.state.value,
                "created_at": process.created_at.isoformat(),
                "updated_at": process.updated_at.isoformat(),
            },
            "tasks": [
                {
                    "id": t.id,
                    "name": definition.get_task(t.task_definition_id).name,
                    "state": t.state.value,
                    "result": t.result,
                    "error": t.error,
                }
                for t in tasks
            ],
            "properties": process.properties,
        }

    async def get_pending_tasks(self, process_id: str) -> list[TaskInstance]:
        """Get all tasks waiting for manual completion."""
        tasks = await self.store.load_tasks_for_process(process_id)
        return [t for t in tasks if t.state == TaskState.READY]

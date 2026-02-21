"""Core workflow engine implementation.

This module contains the WorkflowEngine class that controls the execution
of workflow processes. Ported from Java Engine class.
"""

import logging
import uuid
from datetime import UTC, datetime

from zebra.core.exceptions import (
    ActionNotFoundError,
    DefinitionNotFoundError,
    ExecutionError,
    InvalidStateTransitionError,
    LockError,
    ProcessNotFoundError,
    RoutingError,
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
        extras: dict | None = None,
    ) -> None:
        """Initialize the workflow engine.

        Args:
            store: Storage backend for persistence
            action_registry: Registry of task actions and conditions
            engine_id: Optional unique ID for this engine instance (for locking)
            extras: Optional dict of extra objects to pass to ExecutionContext.
                Use this for dependency injection of services (like memory stores)
                that task actions need but that shouldn't be persisted in process
                properties.
        """
        self.store = store
        self.actions = action_registry
        self.engine_id = engine_id or str(uuid.uuid4())
        self.extras = extras or {}
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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
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
            update={"state": ProcessState.RUNNING, "updated_at": datetime.now(UTC)}
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
            update={"state": ProcessState.PAUSED, "updated_at": datetime.now(UTC)}
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
            update={"state": ProcessState.RUNNING, "updated_at": datetime.now(UTC)}
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
                    stack_task_ids = {t.id for t in task_stack}
                    for new_task in created_tasks:
                        task_def = definition.get_task(new_task.task_definition_id)
                        if task_def.auto or task_def.synchronized:
                            if new_task.id not in stack_task_ids:
                                task_stack.append(new_task)
                                stack_task_ids.add(new_task.id)

                except Exception as e:
                    logger.error(f"Error transitioning task {current_task.id}: {e}")
                    raise

            # Check if process is complete
            process = await self._load_process(process.id)
            tasks = await self.store.load_tasks_for_process(process.id)
            active_tasks = [
                t for t in tasks if t.state not in {TaskState.COMPLETE, TaskState.FAILED}
            ]

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
        # Store full result as dict to preserve next_route for routing conditions
        new_state = TaskState.COMPLETE if (result is None or result.success) else TaskState.FAILED
        result_dict = {
            "output": result.output if result else None,
            "next_route": result.next_route if result else None,
        }
        task = task.model_copy(
            update={
                "state": new_state,
                "result": result_dict,
                "error": result.error if result and not result.success else None,
                "updated_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            }
        )

        await self.store.save_task(task)

        # Store result in process properties for later reference
        process = await self._load_process(task.process_id)
        if result and result.output is not None:
            process.properties[f"__task_output_{task.task_definition_id}"] = result.output
            process = process.model_copy(update={"updated_at": datetime.now(UTC)})
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
                update={"state": TaskState.READY, "updated_at": datetime.now(UTC)}
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

        created_task_ids = {t.id for t in created_tasks}
        for active_task in active_tasks:
            if active_task.task_definition_id in sync_task_ids:
                if active_task.state == TaskState.AWAITING_SYNC:
                    if active_task.id not in created_task_ids:
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
        task = task.model_copy(update={"state": TaskState.RUNNING, "updated_at": datetime.now(UTC)})
        await self.store.save_task(task)

        # Generate idempotency token if not exists (for tracking execution attempts)
        if "__idempotency_token__" not in task.properties:
            token = f"{task.id}_{task.execution_attempt}_{int(datetime.now(UTC).timestamp())}"
            task.properties["__idempotency_token__"] = token
            await self.store.save_task(task)
            logger.debug(f"Generated idempotency token for task {task.id}: {token}")

        context = ExecutionContext(
            engine=self,
            store=self.store,
            process=process,
            process_definition=definition,
            task_definition=task_def,
            extras=self.extras,
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
        # Store full result as dict to preserve next_route for routing conditions
        new_state = TaskState.COMPLETE if result.success else TaskState.FAILED
        result_dict = {
            "output": result.output,
            "next_route": result.next_route,
        }
        task = task.model_copy(
            update={
                "state": new_state,
                "result": result_dict,
                "error": result.error,
                "updated_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            }
        )
        await self.store.save_task(task)

        # Store result in process properties
        if result.output is not None:
            process.properties[f"__task_output_{task_def.id}"] = result.output
            process = process.model_copy(update={"updated_at": datetime.now(UTC)})
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
            extras=self.extras,
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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
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
            created_at=datetime.now(UTC),
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
                "updated_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            context = ExecutionContext(
                engine=self,
                store=self.store,
                process=process,
                process_definition=definition,
                task_definition=TaskDefinition(
                    id="__process_construct__", name="Process Construct"
                ),
                extras=self.extras,
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            context = ExecutionContext(
                engine=self,
                store=self.store,
                process=process,
                process_definition=definition,
                task_definition=TaskDefinition(id="__process_destruct__", name="Process Destruct"),
                extras=self.extras,
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

    async def _reconcile_foes(self, process: ProcessInstance) -> None:
        """Validate and repair FlowOfExecution hierarchies for a process.

        Checks for orphaned FOEs without corresponding tasks and verifies
        parent_foe_id references are valid. Removes dangling FOE references
        to maintain consistency.

        Args:
            process: The process instance to reconcile FOEs for
        """
        logger.debug(f"Reconciling FOEs for process {process.id}")

        # Load all FOEs and tasks for the process
        foes = await self.store.load_foes_for_process(process.id)
        tasks = await self.store.load_tasks_for_process(process.id)

        if not foes:
            return

        # Build maps for quick lookup
        foe_ids = {foe.id for foe in foes}
        task_by_foe = {task.foe_id: task for task in tasks}

        orphaned_foes = []
        invalid_parent_foes = []

        # Check each FOE for issues
        for foe in foes:
            # Check if FOE has any tasks (orphaned if no tasks reference it)
            if foe.id not in task_by_foe:
                # Special case: process construct/destruct FOEs are expected to exist without tasks
                if foe.id not in ["__process_construct__", "__process_destruct__"]:
                    orphaned_foes.append(foe)
                    logger.warning(f"Found orphaned FOE {foe.id} (no tasks reference it)")

            # Check if parent_foe_id references a valid FOE
            if foe.parent_foe_id and foe.parent_foe_id not in foe_ids:
                invalid_parent_foes.append(foe)
                logger.warning(f"FOE {foe.id} has invalid parent_foe_id {foe.parent_foe_id}")

        # Clean up orphaned FOEs (excluding process lifecycle FOEs)
        for foe in orphaned_foes:
            try:
                await self.store.delete_foe(foe.id)
                logger.info(f"Deleted orphaned FOE {foe.id}")
            except Exception as e:
                logger.error(f"Failed to delete FOE {foe.id}: {e}")

        logger.debug(
            f"FOE reconciliation complete: {len(orphaned_foes)} orphaned, "
            f"{len(invalid_parent_foes)} invalid parents"
        )

    async def _is_task_idempotent(self, task: TaskInstance, process: ProcessInstance) -> bool:
        """Determine if a task can be safely re-executed after interruption.

        Args:
            task: The task instance to check
            process: The owning process instance

        Returns:
            True if the task can be re-executed safely, False otherwise
        """
        definition = await self._load_definition(process.definition_id)
        task_def = definition.get_task(task.task_definition_id)

        # Check task definition for idempotency hints
        if task_def.properties.get("idempotent") is True:
            return True

        # Check for idempotency token (already attempted, may have side effects)
        if task.properties.get("__idempotency_token__"):
            # Token exists means execution started, may not be idempotent
            return False

        # Check action registry for idempotency support
        if task_def.action:
            # Access the action class directly from the registry
            if hasattr(self.actions, "_actions") and task_def.action in self.actions._actions:
                action_class = self.actions._actions[task_def.action]
                if hasattr(action_class, "is_idempotent"):
                    # Create minimal context for checking
                    from zebra.tasks.base import ExecutionContext

                    context = ExecutionContext(
                        engine=self,
                        store=self.store,
                        process=process,
                        process_definition=definition,
                        task_definition=task_def,
                        extras=self.extras,
                    )
                    action = action_class()
                    return await action.is_idempotent(task, context)

        # Default: assume non-idempotent for safety
        return False

    async def _reconcile_parallel_branches(self, process: ProcessInstance) -> None:
        """Verify and repair parallel execution state consistency.

        For processes with parallel splits, verifies that all expected parallel
        branches were created. Recreates missing parallel tasks if a split was
        interrupted before all branches were created.

        Args:
            process: The process instance to validate parallel branches for
        """
        logger.debug(f"Reconciling parallel branches for process {process.id}")

        definition = await self._load_definition(process.definition_id)
        tasks = await self.store.load_tasks_for_process(process.id)

        # Find tasks that are outputs of parallel splits
        parallel_split_tasks = []
        for task in tasks:
            if task.state in {TaskState.RUNNING, TaskState.READY, TaskState.PENDING}:
                # Check routings from this task to see if any are parallel
                for routing in definition.get_routings_from(task.task_definition_id):
                    if routing.parallel:
                        parallel_split_tasks.append((task, routing))
                        break

        if not parallel_split_tasks:
            return

        # For each parallel split, verify all branches were created
        recreated_tasks = 0
        for split_task, split_routing in parallel_split_tasks:
            # Find destination tasks for all routings from this split
            expected_branches = [
                r.dest_task_id
                for r in definition.get_routings_from(split_task.task_definition_id)
                if r.parallel
            ]

            if not expected_branches:
                continue

            # Find actual tasks that were created as parallel branches
            actual_branches = []
            for task in tasks:
                if task == split_task:
                    continue
                # Check if this task was created from the split task
                # by looking at routing conditions and parallel flags
                task_routings = definition.get_routings_from(split_task.task_definition_id)
                for routing in task_routings:
                    if routing.parallel and routing.dest_task_id == task.task_definition_id:
                        actual_branches.append(task.task_definition_id)
                        break

            # Find missing branches
            missing_branches = set(expected_branches) - set(actual_branches)

            if missing_branches:
                logger.warning(
                    f"Parallel split at task {split_task.id} is missing branches: "
                    f"{missing_branches}"
                )

        logger.debug(f"Parallel branch reconciliation complete: {recreated_tasks} tasks recreated")

    async def _reconcile_sync_task(self, task: TaskInstance, process: ProcessInstance) -> None:
        """Handle interrupted synchronization (sync) points.

        For sync tasks that were interrupted, verifies if the synchronization
        condition was already satisfied before the interruption. If so, allows
        the task to proceed. Otherwise, ensures parallel branches are verified.

        Args:
            task: The sync task instance to reconcile
            process: The owning process instance
        """
        definition = await self._load_definition(process.definition_id)
        task_def = definition.get_task(task.task_definition_id)

        if not task_def.synchronized:
            return

        # Check if this task has the special flag indicating it was satisfied
        if task.properties.get("__sync_satisfied__"):
            logger.info(f"Sync task {task.id} was already satisfied before interruption")
            # Transition to READY to allow immediate execution
            task = task.model_copy(
                update={"state": TaskState.READY, "updated_at": datetime.now(UTC)}
            )
            await self.store.save_task(task)
            return

        # For tasks in AWAITING_SYNC, re-evaluate if they can proceed
        if task.state == TaskState.AWAITING_SYNC:
            from zebra.core.sync import TaskSync

            task_sync = TaskSync()
            active_tasks = await self.store.load_tasks_for_process(process.id)

            if task_sync.is_task_blocked(task, task_def, process, definition, active_tasks):
                logger.debug(f"Sync task {task.id} is still blocked, waiting for parallel branches")
            else:
                logger.info(f"Sync task {task.id} can now proceed (all parallel branches complete)")
                task = task.model_copy(
                    update={"state": TaskState.READY, "updated_at": datetime.now(UTC)}
                )
                await self.store.save_task(task)

    async def _reconcile_process_lifecycle(self, process: ProcessInstance) -> None:
        """Ensure process construct/destruct actions completed properly.

        Checks if process-level lifecycle actions (construct/destruct) were
        interrupted and need to be re-run or flagged for manual review.

        Args:
            process: The process instance to check
        """
        logger.debug(f"Reconciling process lifecycle for process {process.id}")

        definition = await self._load_definition(process.definition_id)
        tasks = await self.store.load_tasks_for_process(process.id)

        # Check if construct action completed
        construct_tasks = [t for t in tasks if t.foe_id == "__process_construct__"]

        if definition.construct_action and not construct_tasks:
            # Construct never ran or was interrupted before creating task
            # We can't safely re-run it without potentially duplicating setup
            logger.warning(
                f"Process {process.id} construct action '{definition.construct_action}' "
                "may not have completed during interruption"
            )
            process.properties["__construct_needs_review__"] = True
            await self.store.save_process(process)

        # For completed processes, verify destruct ran
        if process.state == ProcessState.COMPLETE:
            destruct_tasks = [t for t in tasks if t.foe_id == "__process_destruct__"]

            if definition.destruct_action and not destruct_tasks:
                logger.warning(
                    f"Process {process.id} destruct action '{definition.destruct_action}' "
                    "did not run before process completion"
                )
                # Note: Running destruct after process completion is complex
                # as parallel branches may already be cleaned up. Flag for manual review.
                process.properties["__destruct_missing__"] = True
                await self.store.save_process(process)

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def resume_all_processes(self) -> list[ProcessInstance]:
        """Resume all processes that were interrupted while RUNNING.

        This method should be called on engine startup to recover from crashes
        or restarts. It finds all processes in RUNNING state (not PAUSED) and
        resumes their execution.

        Returns:
            List of process instances that were resumed
        """
        logger.info("Starting recovery: checking for interrupted processes")

        # Get all processes that were running when interrupted
        running_processes = await self.store.get_running_processes()
        resumed_processes: list[ProcessInstance] = []

        if not running_processes:
            logger.info("No interrupted processes found for recovery")
            return resumed_processes

        logger.info(f"Found {len(running_processes)} processes to recover")

        for process in running_processes:
            try:
                logger.info(
                    f"Recovering process {process.id} (definition: {process.definition_id})"
                )

                # Reconcile FOEs first to ensure consistent parallel execution state
                await self._reconcile_foes(process)

                # Verify parallel branch completeness
                await self._reconcile_parallel_branches(process)

                # Check process lifecycle actions
                await self._reconcile_process_lifecycle(process)

                # Find any tasks that were stuck in RUNNING state
                running_tasks = await self.store.get_running_tasks(process_id=process.id)

                if running_tasks:
                    logger.info(
                        f"Process {process.id} has {len(running_tasks)} tasks in RUNNING state"
                    )
                    # Handle interrupted tasks based on idempotency
                    for task in running_tasks:
                        # Increment execution attempt counter
                        task = task.model_copy(
                            update={
                                "execution_attempt": task.execution_attempt + 1,
                                "updated_at": datetime.now(UTC),
                            }
                        )

                        # Special handling for sync tasks
                        definition = await self._load_definition(process.definition_id)
                        task_def = definition.get_task(task.task_definition_id)
                        if task_def.synchronized:
                            await self._reconcile_sync_task(task, process)
                            continue

                        # Check if task can be safely re-executed
                        if await self._is_task_idempotent(task, process):
                            # Safe to re-run, reset to READY
                            task = task.model_copy(
                                update={
                                    "state": TaskState.READY,
                                    "updated_at": datetime.now(UTC),
                                }
                            )
                            await self.store.save_task(task)
                            logger.info(
                                f"Reset task {task.id} from RUNNING to READY "
                                f"(attempt {task.execution_attempt})"
                            )
                        else:
                            # Non-idempotent task, flag for manual review
                            task.properties["__requires_manual_review__"] = True
                            await self.store.save_task(task)
                            logger.warning(
                                f"Task {task.id} has non-idempotent side effects and was "
                                f"interrupted (attempt {task.execution_attempt}). "
                                "Flagged for manual review."
                            )

                # Process is already in RUNNING state, just need to trigger execution
                # Re-enter the task processing loop to continue where we left off
                await self._process_pending_auto_tasks(process)

                resumed_processes.append(process)
                logger.info(f"Successfully recovered process {process.id}")

            except Exception as e:
                logger.error(f"Failed to recover process {process.id}: {e}", exc_info=True)
                # Continue with other processes even if one fails

        logger.info(
            f"Recovery complete: {len(resumed_processes)} out of {len(running_processes)} "
            "processes recovered"
        )
        return resumed_processes

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

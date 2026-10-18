"""Core data models for the Zebra workflow engine.

This module defines the data structures used throughout the workflow engine,
including both definition models (workflow blueprints) and runtime state models.
"""

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


def _validate_json_serializable(properties: dict[str, Any], context: str) -> None:
    """Validate that a properties dict is JSON-serializable.

    Properties are persisted to storage via json.dumps(), so all values must be
    JSON-serializable (strings, numbers, booleans, lists, dicts, and None).

    Args:
        properties: The properties dict to validate.
        context: A description of the model/field for error messages.

    Raises:
        ValueError: If any value in the dict is not JSON-serializable.
    """
    if not properties:
        return
    try:
        json.dumps(properties)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Properties on {context} must be JSON-serializable "
            f"(strings, numbers, booleans, lists, dicts, and None). "
            f"Serialization failed: {e}"
        ) from e


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


# =============================================================================
# Process and Task States (Runtime)
# =============================================================================


class ProcessState(str, Enum):
    """State machine for process instances.

    Lifecycle: CREATED -> RUNNING -> COMPLETE
                           |-> PAUSED -> RUNNING
                           |-> FAILED
    """

    CREATED = "created"  # Initial state after instantiation
    RUNNING = "running"  # Active execution
    PAUSED = "paused"  # Suspended, can be resumed
    COMPLETE = "complete"  # Terminal state - success
    FAILED = "failed"  # Terminal state - error


class TaskState(str, Enum):
    """State machine for task instances.

    Lifecycle for auto tasks: PENDING -> READY -> RUNNING -> COMPLETE
    Lifecycle for sync tasks: PENDING -> AWAITING_SYNC -> READY -> RUNNING -> COMPLETE
    Suspended tasks: RUNNING -> AWAITING_SUBFLOW -> READY -> RUNNING -> ... (#146)
    Manual tasks wait in READY state until explicitly transitioned.
    """

    PENDING = "pending"  # Created but not yet processed
    AWAITING_SYNC = "awaiting_sync"  # Waiting for parallel branches (join point)
    AWAITING_SUBFLOW = "awaiting_subflow"  # Suspended until its child processes finish
    READY = "ready"  # Ready to execute (manual tasks wait here)
    RUNNING = "running"  # Currently executing
    COMPLETE = "complete"  # Terminal state - success
    FAILED = "failed"  # Terminal state - error


# =============================================================================
# Definition Models (Workflow Blueprints)
# =============================================================================


class TaskDefinition(BaseModel):
    """Definition of a task within a workflow.

    Corresponds to Java ITaskDefinition. Defines the blueprint for a task
    including its behavior (auto vs manual), synchronization, and action class.
    """

    id: str = Field(..., description="Unique identifier for this task within the process")
    name: str = Field(..., description="Human-readable name for the task")
    auto: bool = Field(
        default=True,
        description="If True, task executes automatically. If False, waits for manual transition.",
    )
    synchronized: bool = Field(
        default=False,
        description="If True, this is a join point that waits for all incoming parallel branches.",
    )
    action: str | None = Field(
        default=None, description="Name of the TaskAction to execute (registered in ActionRegistry)"
    )
    construct_action: str | None = Field(
        default=None, description="Action to run before task execution (setup)"
    )
    destruct_action: str | None = Field(
        default=None, description="Action to run after task completion (cleanup)"
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Task-specific configuration properties. "
        "Values must be JSON-serializable (strings, numbers, booleans, lists, dicts, null).",
    )

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _check_properties_serializable(self) -> "TaskDefinition":
        _validate_json_serializable(self.properties, "TaskDefinition")
        return self


class RoutingDefinition(BaseModel):
    """Definition of a routing (edge) between tasks.

    Corresponds to Java IRoutingDefinition. Defines how execution flows
    from one task to another, with optional conditions and parallel execution.
    """

    id: str = Field(..., description="Unique identifier for this routing")
    source_task_id: str = Field(..., description="ID of the originating task")
    dest_task_id: str | None = Field(
        default=None,
        description="ID of the destination task; None = terminal (end workflow branch)",
    )
    parallel: bool = Field(
        default=False,
        description="If True, this routing executes in parallel with others. Creates new FOE.",
    )
    condition: str | None = Field(
        default=None,
        description="Name of ConditionAction to evaluate. If None, routing always fires.",
    )
    name: str | None = Field(
        default=None, description="Optional name for the routing (used by some condition actions)"
    )

    model_config = {"frozen": True}


class ProcessDefinition(BaseModel):
    """Definition of a complete workflow process.

    Corresponds to Java IProcessDefinition. This is the blueprint for a
    workflow, containing all task and routing definitions.
    """

    id: str = Field(..., description="Unique identifier for this process definition")
    name: str = Field(..., description="Human-readable name for the workflow")
    version: int = Field(default=1, description="Version number for the definition")
    first_task_id: str = Field(..., description="ID of the entry point task")
    tasks: dict[str, TaskDefinition] = Field(..., description="Map of task ID to task definition")
    routings: list[RoutingDefinition] = Field(
        default_factory=list, description="List of routing definitions"
    )
    construct_action: str | None = Field(
        default=None, description="Action to run when process starts"
    )
    destruct_action: str | None = Field(
        default=None, description="Action to run when process completes"
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Process-level configuration properties. "
        "Values must be JSON-serializable (strings, numbers, booleans, lists, dicts, null).",
    )

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _check_properties_serializable(self) -> "ProcessDefinition":
        _validate_json_serializable(self.properties, "ProcessDefinition")
        return self

    def get_task(self, task_id: str) -> TaskDefinition:
        """Get a task definition by ID."""
        if task_id not in self.tasks:
            raise KeyError(f"Task '{task_id}' not found in process '{self.id}'")
        return self.tasks[task_id]

    def get_routings_from(self, task_id: str) -> list[RoutingDefinition]:
        """Get all outgoing routings from a task."""
        return [r for r in self.routings if r.source_task_id == task_id]

    def get_routings_to(self, task_id: str) -> list[RoutingDefinition]:
        """Get all incoming routings to a task."""
        return [r for r in self.routings if r.dest_task_id == task_id]


# =============================================================================
# Runtime State Models (Instances)
# =============================================================================


class FlowOfExecution(BaseModel):
    """Tracks a single execution path through the workflow.

    Corresponds to Java IFOE. When a workflow splits into parallel branches,
    each branch gets its own FOE. When branches join (sync point), FOEs are
    merged. This enables tracking of parallel execution and proper synchronization.
    """

    id: str = Field(..., description="Unique identifier for this FOE")
    process_id: str = Field(..., description="ID of the owning process instance")
    parent_foe_id: str | None = Field(
        default=None, description="Parent FOE ID (for tracking lineage)"
    )
    created_at: datetime = Field(default_factory=_utc_now)

    model_config = {"from_attributes": True}


class TaskInstance(BaseModel):
    """Runtime instance of a task within a running process.

    Corresponds to Java ITaskInstance. Represents the current state of a
    specific task execution, including its FOE for parallel tracking.
    """

    id: str = Field(..., description="Unique identifier for this task instance")
    process_id: str = Field(..., description="ID of the owning process instance")
    task_definition_id: str = Field(..., description="ID of the task definition")
    state: TaskState = Field(default=TaskState.PENDING)
    foe_id: str = Field(..., description="Flow of Execution ID for parallel tracking")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime properties (can be modified during execution). "
        "Values must be JSON-serializable (strings, numbers, booleans, lists, dicts, null).",
    )
    result: Any | None = Field(default=None, description="Output from task execution")
    error: str | None = Field(default=None, description="Error message if task failed")
    execution_attempt: int = Field(
        default=0, description="Number of times this task has been executed (for recovery)"
    )
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = Field(default=None)

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _check_properties_serializable(self) -> "TaskInstance":
        _validate_json_serializable(self.properties, "TaskInstance")
        return self


class ProcessInstance(BaseModel):
    """Runtime instance of a workflow process.

    Corresponds to Java IProcessInstance. Represents a running or completed
    workflow execution with all its state.
    """

    id: str = Field(..., description="Unique identifier for this process instance")
    definition_id: str = Field(..., description="ID of the process definition")
    state: ProcessState = Field(default=ProcessState.CREATED)
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime properties accessible to all tasks. "
        "Values must be JSON-serializable (strings, numbers, booleans, lists, dicts, null).",
    )
    parent_process_id: str | None = Field(
        default=None, description="Parent process ID for subflows"
    )
    parent_task_id: str | None = Field(
        default=None, description="Parent task ID that spawned this subflow"
    )
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = Field(default=None)

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _check_properties_serializable(self) -> "ProcessInstance":
        _validate_json_serializable(self.properties, "ProcessInstance")
        return self


class ProcessEventKind(str, Enum):
    """What a journal entry records (#184)."""

    PROCESS_STARTED = "process_started"  # changed = the initial properties
    PROCESS_COMPLETED = "process_completed"
    PROCESS_FAILED = "process_failed"
    TASK_WAITING = "task_waiting"  # a manual task became available
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_SUSPENDED = "task_suspended"  # waiting on subflows (#146)


class ProcessEvent(BaseModel):
    """One entry in a process's step journal (#184).

    The engine appends an event at each process and task lifecycle step. Each
    event carries the process-property changes made since the previous step, so
    replaying a process's events in order rebuilds its properties at any point.
    Task instances are deleted on completion; the journal is what remains.
    """

    id: str = Field(..., description="Unique identifier for this event")
    process_id: str = Field(..., description="ID of the process the event belongs to")
    kind: ProcessEventKind
    task_instance_id: str | None = Field(default=None, description="Task instance, if any")
    task_definition_id: str | None = Field(default=None, description="Task definition, if any")
    attempt: int = Field(default=0, description="Task execution attempt")
    timestamp: datetime = Field(default_factory=_utc_now)
    changed: dict[str, Any] = Field(
        default_factory=dict, description="Process properties set or changed by this step"
    )
    removed: list[str] = Field(
        default_factory=list, description="Process properties removed by this step"
    )
    error: str | None = Field(default=None)
    next_route: str | None = Field(
        default=None, description="Route the task chose, on task_completed/failed (#170)"
    )

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _check_changed_serializable(self) -> "ProcessEvent":
        _validate_json_serializable(self.changed, "ProcessEvent")
        return self


# =============================================================================
# Task Results
# =============================================================================


class TaskResult(BaseModel):
    """Result from executing a task action.

    Returned by TaskAction.run() to indicate success/failure and provide output.
    """

    success: bool = Field(..., description="Whether the task completed successfully")
    output: Any | None = Field(
        default=None,
        description="Output data from the task. Must be JSON-serializable (strings, numbers, "
        "booleans, lists, dicts, null) as it is stored into process properties for "
        "downstream tasks and persisted to storage.",
    )
    error: str | None = Field(default=None, description="Error message if failed")
    next_route: str | None = Field(
        default=None,
        description="For decision tasks: name of the routing to follow (overrides conditions)",
    )
    suspend_children: list[str] | None = Field(
        default=None,
        description="Child process ids to wait for. When set, the task suspends in "
        "AWAITING_SUBFLOW and its action is re-run once every child is terminal (#146).",
    )

    @classmethod
    def ok(cls, output: Any = None) -> "TaskResult":
        """Create a successful result."""
        return cls(success=True, output=output)

    @classmethod
    def fail(cls, error: str) -> "TaskResult":
        """Create a failed result."""
        return cls(success=False, error=error)

    @classmethod
    def suspend(cls, children: list[str]) -> "TaskResult":
        """Suspend the task until the given child processes are terminal.

        The children must be processes the action created (left in CREATED, or
        already started) with ``parent_task_id`` set to this task. The engine
        starts any still in CREATED, then re-runs the action with
        ``context.subflow_results`` once all of them are COMPLETE or FAILED.
        """
        if not children:
            raise ValueError("suspend() needs at least one child process id")
        return cls(success=True, suspend_children=list(children))

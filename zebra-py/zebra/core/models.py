"""Core data models for the Zebra workflow engine.

This module defines the data structures used throughout the workflow engine,
including both definition models (workflow blueprints) and runtime state models.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


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
    Manual tasks wait in READY state until explicitly transitioned.
    """

    PENDING = "pending"  # Created but not yet processed
    AWAITING_SYNC = "awaiting_sync"  # Waiting for parallel branches (join point)
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
        default=True, description="If True, task executes automatically. If False, waits for manual transition."
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
        default_factory=dict, description="Task-specific configuration properties"
    )

    model_config = {"frozen": True}


class RoutingDefinition(BaseModel):
    """Definition of a routing (edge) between tasks.

    Corresponds to Java IRoutingDefinition. Defines how execution flows
    from one task to another, with optional conditions and parallel execution.
    """

    id: str = Field(..., description="Unique identifier for this routing")
    source_task_id: str = Field(..., description="ID of the originating task")
    dest_task_id: str = Field(..., description="ID of the destination task")
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
    tasks: dict[str, TaskDefinition] = Field(
        ..., description="Map of task ID to task definition"
    )
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
        default_factory=dict, description="Process-level configuration properties"
    )

    model_config = {"frozen": True}

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
        default_factory=dict, description="Runtime properties (can be modified during execution)"
    )
    result: Any | None = Field(default=None, description="Output from task execution")
    error: str | None = Field(default=None, description="Error message if task failed")
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = Field(default=None)

    model_config = {"from_attributes": True}


class ProcessInstance(BaseModel):
    """Runtime instance of a workflow process.

    Corresponds to Java IProcessInstance. Represents a running or completed
    workflow execution with all its state.
    """

    id: str = Field(..., description="Unique identifier for this process instance")
    definition_id: str = Field(..., description="ID of the process definition")
    state: ProcessState = Field(default=ProcessState.CREATED)
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Runtime properties accessible to all tasks"
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


# =============================================================================
# Task Results
# =============================================================================


class TaskResult(BaseModel):
    """Result from executing a task action.

    Returned by TaskAction.run() to indicate success/failure and provide output.
    """

    success: bool = Field(..., description="Whether the task completed successfully")
    output: Any | None = Field(default=None, description="Output data from the task")
    error: str | None = Field(default=None, description="Error message if failed")
    next_route: str | None = Field(
        default=None,
        description="For decision tasks: name of the routing to follow (overrides conditions)",
    )

    @classmethod
    def ok(cls, output: Any = None) -> "TaskResult":
        """Create a successful result."""
        return cls(success=True, output=output)

    @classmethod
    def fail(cls, error: str) -> "TaskResult":
        """Create a failed result."""
        return cls(success=False, error=error)

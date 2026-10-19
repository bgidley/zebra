"""Metrics dataclasses and in-memory storage for workflow performance tracking.

This module provides:
- Data classes for workflow runs, task executions, and stats
- In-memory storage implementation (via re-export)

For custom storage backends, implement the MetricsStore interface from
zebra_agent.storage.interfaces.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebra.core.models import ProcessInstance
    from zebra.storage.base import StateStore

    from zebra_agent.storage.interfaces import MetricsStore

logger = logging.getLogger(__name__)


#: Most processes one run's tree is searched for (root, subflows, tool calls).
MAX_RUN_PROCESSES = 500


async def run_process_ids(store: StateStore, root_id: str) -> list[str]:
    """The run's root process and every descendant (subflows, tool calls), breadth first."""
    ids, frontier = [root_id], [root_id]
    while frontier and len(ids) < MAX_RUN_PROCESSES:
        children = []
        for process_id in frontier:
            children.extend(c.id for c in await store.list_child_processes(process_id))
        ids.extend(children)
        frontier = children
    return ids[:MAX_RUN_PROCESSES]


async def record_run_totals(
    metrics: MetricsStore | None, store: StateStore | None, process: ProcessInstance
) -> bool:
    """Set a finished goal's run record to everything its process tree spent (#206).

    ``assess_and_record`` records only the goal workflow's cost; the Agent Main Loop's own
    calls (selection, gates, assessment, memory, knowledge) and any retries are missed.
    The spend ledger has each call once with its process, so the run's spend is the
    ledger sum over the root and its descendants. A store without a ledger falls back
    to the root's ``__total_cost__`` plus the goal workflow's cost. Never raises.
    """
    props = process.properties or {}
    run_id = props.get("run_id")
    if metrics is None or not run_id:
        return False
    try:
        totals = None
        if store is not None:
            totals = await metrics.get_spend_for_processes(await run_process_ids(store, process.id))
        if totals is None:
            history = props.get("__token_history__") or []
            child = props.get("execution_result") or {}
            totals = (
                float(props.get("__total_cost__") or 0.0) + float(child.get("cost") or 0.0),
                sum(int(h.get("input") or 0) for h in history)
                + int(child.get("input_tokens") or 0),
                sum(int(h.get("output") or 0) for h in history)
                + int(child.get("output_tokens") or 0),
            )
        cost, input_tokens, output_tokens = totals
        return await metrics.update_run_totals(
            run_id, cost=cost, input_tokens=input_tokens, output_tokens=output_tokens
        )
    except Exception:  # noqa: BLE001 - bookkeeping never fails a goal
        logger.warning("Could not record run totals for %s", run_id, exc_info=True)
        return False
    history = props.get("__token_history__") or []
    try:
        return await metrics.update_run_totals(
            run_id,
            cost=float(props.get("__total_cost__") or 0.0),
            input_tokens=sum(int(h.get("input") or 0) for h in history),
            output_tokens=sum(int(h.get("output") or 0) for h in history),
        )
    except Exception:  # noqa: BLE001 - bookkeeping never fails a goal
        logger.warning("Could not record run totals for %s", run_id, exc_info=True)
        return False


@dataclass
class WorkflowRun:
    """Record of a single workflow execution."""

    id: str
    workflow_name: str
    goal: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    user_rating: int | None = None  # 1-5
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0  # USD cost of this run
    error: str | None = None
    output: Any = None
    model: str | None = None  # LLM model used (e.g. "deepseek/deepseek-v4.1-flash")
    extends_run_id: str | None = None  # F116: run this one follows up on
    # F134/F135: continuation of a previous run (extends_run_id is the predecessor)
    continuation_comment: str | None = None  # user's "where it got to / what next"
    continuation_decision: str | None = None  # same_workflow|existing_workflow|new_workflow
    continuation_rationale: str | None = None  # why the assessor chose that route
    user_id: int | None = None  # F153: owner of the run (None = unowned / single-user)

    @classmethod
    def create(cls, workflow_name: str, goal: str) -> "WorkflowRun":
        """Create a new workflow run with auto-generated ID and timestamp.

        Args:
            workflow_name: Name of the workflow being executed
            goal: The user's goal or request

        Returns:
            A new WorkflowRun instance
        """
        return cls(
            id=str(uuid.uuid4()),
            workflow_name=workflow_name,
            goal=goal,
            started_at=datetime.now(UTC),
        )


@dataclass
class TaskExecution:
    """Record of a single task execution within a workflow run."""

    id: str
    run_id: str  # Foreign key to WorkflowRun.id
    task_definition_id: str  # Task ID from definition (e.g., "analyze")
    task_name: str  # Human-readable name
    execution_order: int  # Order in execution sequence (1-based)
    state: str  # "running" | "complete" | "failed" | "skipped"
    started_at: datetime
    completed_at: datetime | None = None
    output: Any = None  # Task result/output
    error: str | None = None  # Error message if failed

    @classmethod
    def create(
        cls,
        run_id: str,
        task_definition_id: str,
        task_name: str,
        execution_order: int,
    ) -> "TaskExecution":
        """Create a new task execution record with auto-generated ID and timestamp.

        Args:
            run_id: ID of the parent workflow run
            task_definition_id: Task ID from the workflow definition
            task_name: Human-readable task name
            execution_order: Order in the execution sequence (1-based)

        Returns:
            A new TaskExecution instance in "running" state
        """
        return cls(
            id=str(uuid.uuid4()),
            run_id=run_id,
            task_definition_id=task_definition_id,
            task_name=task_name,
            execution_order=execution_order,
            state="running",
            started_at=datetime.now(UTC),
        )


@dataclass
class WorkflowStats:
    """Aggregated statistics for a workflow."""

    workflow_name: str
    total_runs: int = 0
    successful_runs: int = 0
    avg_rating: float | None = None
    last_used: datetime | None = None
    continued_runs: int = 0  # runs that a later run continues (extends_run_id → this run)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a fraction (0.0 to 1.0)."""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs

    @property
    def continuation_rate(self) -> float:
        """Fraction of runs the user had to continue (0.0 to 1.0) — F136/#137."""
        if self.total_runs == 0:
            return 0.0
        return self.continued_runs / self.total_runs


@dataclass
class GymScore:
    """One golden task scored against one version of a workflow (#171).

    ``variant`` is ``current`` (the library version) or ``candidate`` (a staged
    self-modification). ``score`` is 0 to 1, or None when the judge could not
    score the output. ``details`` holds per-criterion verdicts, the judge's
    reasoning, an output excerpt and, for candidates, the gate decision.
    """

    id: str
    gym_run_id: str  # Process id of the gym task's process (Dream Cycle or Golden Gym)
    golden_id: str
    workflow_name: str
    variant: str  # "current" | "candidate"
    score: float | None
    created_at: datetime
    error: str | None = None
    details: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        gym_run_id: str,
        golden_id: str,
        workflow_name: str,
        variant: str,
        score: float | None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "GymScore":
        """Create a score record with a new id and the current time."""
        return cls(
            id=str(uuid.uuid4()),
            gym_run_id=gym_run_id,
            golden_id=golden_id,
            workflow_name=workflow_name,
            variant=variant,
            score=score,
            created_at=datetime.now(UTC),
            error=error,
            details=details,
        )


def __getattr__(name: str):
    """Lazy import for MetricsStore to avoid circular import."""
    if name == "MetricsStore":
        from zebra_agent.storage.metrics import InMemoryMetricsStore

        return InMemoryMetricsStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "WorkflowRun",
    "TaskExecution",
    "WorkflowStats",
    "GymScore",
    "MetricsStore",  # noqa: F822 - resolved via __getattr__ (backward-compat alias for InMemoryMetricsStore)
]

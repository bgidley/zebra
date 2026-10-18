"""Step-by-step trace of a run across its parent and subflow processes (#184).

Builds the tree behind the trace page from the engine's step journal
(``ProcessEvent``) and the live task instances: one node per process, its
steps in the order they started, and each subflow nested under the step that
spawned it (``parent_task_id``). ``properties_at`` rebuilds a process's
properties as they stood after any journalled step.

Only uses the ``StateStore`` interface, so it works with any store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from zebra.core import journal
from zebra.core.models import (
    ProcessEvent,
    ProcessEventKind,
    ProcessInstance,
    ProcessState,
    TaskInstance,
    TaskState,
)
from zebra.core.replay import REPLAY_KEY
from zebra.storage.base import StateStore

#: Most processes one trace loads; deeper or wider trees are cut off and flagged.
MAX_TRACE_PROCESSES = 200

#: Most parent links followed when climbing to a root or descending to subflows.
MAX_TRACE_DEPTH = 10

#: Step states that mean "this is where the run is now".
CURRENT_STATES = frozenset({"running", "waiting", "suspended", "queued"})

_TERMINAL = frozenset({ProcessState.COMPLETE, ProcessState.FAILED})

_LIVE_STATE = {
    TaskState.RUNNING: "running",
    TaskState.READY: "queued",
    TaskState.PENDING: "queued",
    TaskState.AWAITING_SYNC: "queued",
    TaskState.AWAITING_SUBFLOW: "suspended",
    TaskState.FAILED: "failed",
    TaskState.COMPLETE: "complete",
}


@dataclass
class TraceStep:
    """One task instance's run: from first start (or wait) to its last event."""

    task_instance_id: str
    task_definition_id: str
    name: str
    state: str  # running | waiting | suspended | queued | complete | failed | interrupted
    started_at: datetime | None = None
    ended_at: datetime | None = None
    attempts: int = 0
    changed: dict[str, Any] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    error: str | None = None
    last_event_id: str | None = None
    children: list[TraceProcess] = field(default_factory=list)

    @property
    def is_current(self) -> bool:
        return self.state in CURRENT_STATES

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    @property
    def changed_keys(self) -> list[str]:
        return sorted(self.changed)


@dataclass
class TraceProcess:
    """One process in the trace tree."""

    id: str
    definition_id: str
    name: str
    state: str
    created_at: datetime
    completed_at: datetime | None
    error: str | None
    depth: int
    steps: list[TraceStep] = field(default_factory=list)
    unlinked_children: list[TraceProcess] = field(default_factory=list)
    has_journal: bool = False
    start_event_id: str | None = None
    replay_of: str | None = None  # the process this one replays (#170)
    replay_live: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.state in (ProcessState.RUNNING.value, ProcessState.CREATED.value)

    @property
    def can_replay(self) -> bool:
        """Finished with a step journal, so it can be replayed (#170)."""
        return self.has_journal and not self.is_active

    @property
    def step_choices(self) -> list[tuple[str, str]]:
        """Distinct ``(step id, name)`` of the steps it ran, in order: the live choices."""
        seen: dict[str, str] = {}
        for step in self.steps:
            seen.setdefault(step.task_definition_id, step.name)
        return list(seen.items())

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None


@dataclass
class RunTrace:
    """The whole tree plus where the run is now."""

    root: TraceProcess
    current: list[list[str]]  # each: names from the root process down to an active step
    process_count: int
    step_count: int
    truncated: bool

    @property
    def is_active(self) -> bool:
        return self.root.is_active


async def find_root(store: StateStore, process_id: str) -> ProcessInstance | None:
    """Return the top-level ancestor of *process_id* (itself if it has no parent)."""
    process = await store.load_process(process_id)
    for _ in range(MAX_TRACE_DEPTH):
        if process is None or not process.parent_process_id:
            return process
        parent = await store.load_process(process.parent_process_id)
        if parent is None:
            return process
        process = parent
    return process


async def find_run_root(store: StateStore, run_id: str) -> ProcessInstance | None:
    """Return the top-level process carrying ``run_id`` in its properties."""
    for state in (
        ProcessState.RUNNING,
        ProcessState.CREATED,
        ProcessState.COMPLETE,
        ProcessState.FAILED,
    ):
        for proc in await store.get_processes_by_state(state):
            if (proc.properties or {}).get("run_id") == run_id and not proc.parent_process_id:
                return proc
    return None


async def build_trace(store: StateStore, root: ProcessInstance) -> RunTrace:
    """Build the trace tree rooted at *root*."""
    processes, truncated = await _collect_tree(store, root)
    ids = [p.id for p, _ in processes]
    events = await store.load_process_events(ids)
    by_process: dict[str, list[ProcessEvent]] = {pid: [] for pid in ids}
    for event in events:
        by_process.setdefault(event.process_id, []).append(event)

    nodes: dict[str, TraceProcess] = {}
    for process, depth in processes:
        live = [] if process.state in _TERMINAL else await store.load_tasks_for_process(process.id)
        names = await _task_names(store, process.definition_id)
        nodes[process.id] = _process_node(
            process, depth, by_process.get(process.id, []), live, names
        )

    # Nest each subflow under the step that spawned it.
    for process, _ in processes:
        if process.id == root.id:
            continue
        parent = nodes.get(process.parent_process_id or "")
        if parent is None:
            continue
        step = next((s for s in parent.steps if s.task_instance_id == process.parent_task_id), None)
        (step.children if step else parent.unlinked_children).append(nodes[process.id])

    root_node = nodes[root.id]
    current: list[list[str]] = []
    _collect_current(root_node, [], current)
    return RunTrace(
        root=root_node,
        current=current,
        process_count=len(nodes),
        step_count=sum(len(n.steps) for n in nodes.values()),
        truncated=truncated,
    )


async def properties_at(store: StateStore, process_id: str, event_id: str) -> dict[str, Any] | None:
    """Return *process_id*'s properties as they stood after journal event *event_id*.

    None if the event is not in that process's journal.
    """
    events = await store.load_process_events([process_id])
    states = journal.replay(events)
    for event, state in zip(events, states, strict=True):
        if event.id == event_id:
            return state
    return None


_Items = list[tuple[str, Any]]


def split_properties(properties: dict[str, Any]) -> tuple[_Items, _Items]:
    """Split properties into (workflow, internal ``__``-prefixed) lists, each sorted by key."""
    items = sorted(properties.items())
    return (
        [(k, v) for k, v in items if not k.startswith("__")],
        [(k, v) for k, v in items if k.startswith("__")],
    )


# =============================================================================
# Internals
# =============================================================================


async def _collect_tree(
    store: StateStore, root: ProcessInstance
) -> tuple[list[tuple[ProcessInstance, int]], bool]:
    """Breadth-first list of (process, depth) under *root*, capped in size and depth."""
    found: list[tuple[ProcessInstance, int]] = [(root, 0)]
    seen = {root.id}
    frontier = [(root, 0)]
    truncated = False
    while frontier:
        next_frontier = []
        for process, depth in frontier:
            if depth >= MAX_TRACE_DEPTH:
                truncated = True
                continue
            for child in await store.list_child_processes(process.id):
                if child.id in seen:
                    continue
                if len(found) >= MAX_TRACE_PROCESSES:
                    return found, True
                seen.add(child.id)
                found.append((child, depth + 1))
                next_frontier.append((child, depth + 1))
        frontier = next_frontier
    return found, truncated


async def _task_names(store: StateStore, definition_id: str) -> dict[str, str]:
    """Task id -> name for a definition, plus ``__process__`` -> the workflow name."""
    definition = await store.load_definition(definition_id)
    if definition is None:
        return {}
    names = {tid: (t.name or tid) for tid, t in definition.tasks.items()}
    names["__process__"] = definition.name or definition_id
    return names


def _process_node(
    process: ProcessInstance,
    depth: int,
    events: list[ProcessEvent],
    live: list[TaskInstance],
    names: dict[str, str],
) -> TraceProcess:
    error = process.properties.get("__error__") if process.state == ProcessState.FAILED else None
    node = TraceProcess(
        id=process.id,
        definition_id=process.definition_id,
        name=names.get("__process__", process.definition_id),
        state=process.state.value,
        created_at=process.created_at,
        completed_at=process.completed_at,
        error=str(error) if error else None,
        depth=depth,
        has_journal=bool(events),
    )
    marker = (process.properties or {}).get(REPLAY_KEY)
    if isinstance(marker, dict):
        node.replay_of = marker.get("of")
        node.replay_live = list(marker.get("live") or [])

    steps: dict[str, TraceStep] = {}
    for event in events:
        if event.kind == ProcessEventKind.PROCESS_STARTED:
            node.start_event_id = event.id
            continue
        if event.task_instance_id is None or event.task_definition_id is None:
            continue
        step = steps.get(event.task_instance_id)
        if step is None:
            step = TraceStep(
                task_instance_id=event.task_instance_id,
                task_definition_id=event.task_definition_id,
                name=names.get(event.task_definition_id, event.task_definition_id),
                state="queued",
                started_at=event.timestamp,
            )
            steps[event.task_instance_id] = step
        step.last_event_id = event.id
        _apply(step, event)

    # Live tasks the journal has not seen yet (queued, awaiting sync), or whose
    # state moved on since (a manual task picked up again, a resumed suspension).
    for task in live:
        step = steps.get(task.id)
        if step is None:
            steps[task.id] = TraceStep(
                task_instance_id=task.id,
                task_definition_id=task.task_definition_id,
                name=names.get(task.task_definition_id, task.task_definition_id),
                state=_LIVE_STATE.get(task.state, task.state.value),
                started_at=task.created_at,
                error=task.error,
            )
        elif task.state == TaskState.RUNNING:
            step.state = "running"

    if process.state in _TERMINAL:
        for step in steps.values():
            if step.state in CURRENT_STATES:
                step.state = "interrupted"

    node.steps = sorted(steps.values(), key=lambda s: s.started_at or process.created_at)
    return node


def _apply(step: TraceStep, event: ProcessEvent) -> None:
    """Fold one journal event into its step."""
    kind = event.kind
    if kind == ProcessEventKind.TASK_WAITING:
        step.state = "waiting"
        return
    if kind == ProcessEventKind.TASK_STARTED:
        if step.state != "suspended":  # resuming after subflows is the same run
            step.attempts += 1
        step.state = "running"
        step.ended_at = None
        return
    # Suspended, completed, failed: the step's own property changes.
    step.changed.update(event.changed)
    step.removed = sorted(set(step.removed) | set(event.removed))
    if kind == ProcessEventKind.TASK_SUSPENDED:
        step.state = "suspended"
    elif kind == ProcessEventKind.TASK_COMPLETED:
        step.state = "complete"
        step.ended_at = event.timestamp
        step.attempts = max(step.attempts, 1)
    elif kind == ProcessEventKind.TASK_FAILED:
        step.state = "failed"
        step.ended_at = event.timestamp
        step.error = event.error
        step.attempts = max(step.attempts, 1)


def _collect_current(node: TraceProcess, path: list[str], out: list[list[str]]) -> None:
    """Append the path to every active step that has no active subflow below it."""
    here = [*path, node.name]
    for step in node.steps:
        before = len(out)
        for child in step.children:
            if child.is_active:
                _collect_current(child, [*here, step.name], out)
        # A step waiting on subflows that have not started a step yet is itself current.
        if step.is_current and node.is_active and len(out) == before:
            out.append([*here, step.name])
    for child in node.unlinked_children:
        if child.is_active:
            _collect_current(child, here, out)

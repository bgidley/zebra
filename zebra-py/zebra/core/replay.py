"""Replay a finished process from its step journal (#170).

The journal (#184) records what every task changed in its process. Folding a
task instance's events, after the first (whose diff holds changes made before
the task began), gives exactly that task's effect: the properties it set or
removed, its output, the route it chose, and whether it failed. A replay is a
new process that serves those recorded effects instead of running actions, so
it reproduces the original at no cost. Steps marked live run for real.
"""

from dataclasses import dataclass, field
from typing import Any

from zebra.core import journal
from zebra.core.exceptions import ZebraError
from zebra.core.models import ProcessDefinition, ProcessEvent, ProcessEventKind

#: Process property marking a replay: ``{"of": original id, "live": [step ids],
#: "served": {step id: occurrences served so far}}``.
REPLAY_KEY = "__replay__"

#: LLM spend counters. A replay never copies them, so it records zero cost.
UNREPLAYED_KEYS = frozenset({"__total_cost__", "__total_tokens__", "__token_history__"})

_TASK_END_KINDS = frozenset({ProcessEventKind.TASK_COMPLETED, ProcessEventKind.TASK_FAILED})


class ReplayError(ZebraError):
    """A replay cannot be created (process still running, no history, unknown step)."""


@dataclass(frozen=True)
class RecordedStep:
    """What one task instance of the original process did."""

    task_definition_id: str
    success: bool
    output: Any = None
    next_route: str | None = None
    error: str | None = None
    changed: dict[str, Any] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)

    def truncated_keys(self) -> list[str]:
        """Keys whose recorded value was too large to keep whole."""
        return sorted(
            key
            for key, value in self.changed.items()
            if isinstance(value, dict) and value.get(journal.TRUNCATED_KEY)
        )

    def apply(self, properties: dict[str, Any]) -> None:
        """Apply this step's recorded changes to *properties*, except spend counters."""
        for key in self.removed:
            if key not in UNREPLAYED_KEYS:
                properties.pop(key, None)
        for key, value in self.changed.items():
            if key not in UNREPLAYED_KEYS:
                properties[key] = value


def starting_properties(events: list[ProcessEvent]) -> dict[str, Any] | None:
    """The properties a process started with, or None if it has no journal."""
    for event in events:
        if event.kind == ProcessEventKind.PROCESS_STARTED:
            return dict(event.changed)
    return None


def recorded_steps(
    events: list[ProcessEvent], definition: ProcessDefinition
) -> dict[str, list[RecordedStep]]:
    """Group a process's journal into the steps it ran, per task definition, in order.

    Task instances that never reached ``task_completed`` / ``task_failed``
    (interrupted) are left out. Events from before routes were journalled get
    the route inferred from the step the original ran next.
    """
    states = journal.replay(events)
    by_instance: dict[str, list[int]] = {}
    for i, event in enumerate(events):
        if event.task_instance_id:
            by_instance.setdefault(event.task_instance_id, []).append(i)

    steps: dict[str, list[RecordedStep]] = {}
    for indexes in by_instance.values():
        ends = [i for i in indexes if events[i].kind in _TASK_END_KINDS]
        if not ends:
            continue
        end = ends[-1]
        task_id = events[end].task_definition_id
        # The first event's diff is what happened before the task began.
        folded = [i for i in indexes if i <= end][1:] or [end]
        changed: dict[str, Any] = {}
        removed: set[str] = set()
        for i in folded:
            for key in events[i].removed:
                changed.pop(key, None)
                removed.add(key)
            for key, value in events[i].changed.items():
                changed[key] = value
                removed.discard(key)
        route = events[end].next_route
        if route is None:
            route = _infer_route(events, end, task_id, definition)
        steps.setdefault(task_id, []).append(
            RecordedStep(
                task_definition_id=task_id,
                success=events[end].kind == ProcessEventKind.TASK_COMPLETED,
                output=states[end].get(f"__task_output_{task_id}"),
                next_route=route,
                error=events[end].error,
                changed=changed,
                removed=sorted(removed),
            )
        )
    return steps


def _infer_route(
    events: list[ProcessEvent], end: int, task_id: str, definition: ProcessDefinition
) -> str | None:
    """The named serial routing whose destination the original ran after *end*, if any."""
    if task_id not in definition.tasks:
        return None
    routings = [r for r in definition.get_routings_from(task_id) if r.name and not r.parallel]
    if not routings:
        return None
    by_dest = {r.dest_task_id: r.name for r in routings if r.dest_task_id}
    seen: set[str] = set()
    for event in events[end + 1 :]:
        instance = event.task_instance_id
        if not instance or instance in seen:
            continue
        seen.add(instance)
        if event.task_definition_id in by_dest:
            return by_dest[event.task_definition_id]
    terminal = [r.name for r in routings if r.dest_task_id is None]
    return terminal[0] if len(terminal) == 1 else None


def changed_steps(original: ProcessDefinition, replacement: ProcessDefinition) -> set[str]:
    """Steps of *replacement* that are new or differ from *original* (they run live)."""
    return {
        task_id
        for task_id, task_def in replacement.tasks.items()
        if task_id not in original.tasks or original.tasks[task_id] != task_def
    }


def cannot_serve(task_id: str, occurrence: int, reason: str) -> str:
    """The error a replayed step fails with when the recording cannot serve it."""
    return (
        f"Replay cannot serve step '{task_id}' (run #{occurrence + 1}): {reason}. "
        "Run it live to continue."
    )

"""Every action a workflow definition can run (#230).

A task's ``action`` is not the only code a workflow runs: the engine also runs each
task's ``construct_action`` / ``destruct_action`` and the process-level
``construct_action`` (at start) and ``destruct_action`` (at the end). Safety checks
(the gym's ``unsafe_reason``, the Commons import judge, the supervised-run approval
form) must see all of them, or a workflow could hide an action from its reviewer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from zebra.core.models import ProcessDefinition


@dataclass(frozen=True)
class DefinedAction:
    """One action a definition runs, and where it runs."""

    action: str
    #: Task id, or None for a process-level construct / destruct action.
    task_id: str | None
    #: ``action``, ``construct_action`` or ``destruct_action``.
    slot: str
    #: Human label for review forms and refusal reasons.
    label: str


def definition_actions(definition: ProcessDefinition) -> Iterator[DefinedAction]:
    """Yield every action *definition* can run, process-level ones first."""
    if definition.construct_action:
        yield DefinedAction(definition.construct_action, None, "construct_action", "workflow start")
    for task_id, task_def in definition.tasks.items():
        name = task_def.name or task_id
        if task_def.construct_action:
            yield DefinedAction(
                task_def.construct_action, task_id, "construct_action", f"{name} (before)"
            )
        if task_def.action:
            yield DefinedAction(task_def.action, task_id, "action", name)
        if task_def.destruct_action:
            yield DefinedAction(
                task_def.destruct_action, task_id, "destruct_action", f"{name} (after)"
            )
    if definition.destruct_action:
        yield DefinedAction(definition.destruct_action, None, "destruct_action", "workflow end")


def describe(defined: DefinedAction) -> str:
    """Where *defined* runs, for a refusal reason (``task 'x' construct_action``)."""
    where = f"task '{defined.task_id}'" if defined.task_id else "the workflow"
    return where if defined.slot == "action" else f"{where} {defined.slot}"

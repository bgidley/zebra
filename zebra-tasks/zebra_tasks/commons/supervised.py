"""Supervised use of imported workflows (Zebra Commons S3, #230).

An adopted workflow's ``commons.supervised`` flag is enforced *outside* its YAML: the
publisher wrote that YAML, so it cannot be trusted to gate itself. ``check_launch``
(``zebra_tasks.launch``) asks ``supervision_for`` about every library workflow start;
for a supervised one ``create_library_process`` creates a *Supervised run* wrapper
process instead (``supervised_run_definition``):

1. ``approve_run``: an owner-only human task "Run imported workflow X for this goal?"
   listing the workflow's actions, irreversible ones flagged (``reversibility_hint``).
2. ``apply_decision`` (``commons_supervised_run``): on ``run`` it starts the real
   workflow as its child and suspends on it; on resume it copies the child's result
   onto itself, so the caller sees the workflow's output, and counts the approved
   run (``WorkflowLibrary.record_supervised_run``; the flag clears after
   ``SUPERVISED_RUNS``). Anything else fails the wrapper with
   ``__supervised_rejected__`` (a goal then fails over to another workflow).

Every entry point already starts, suspends on or watches the process it gets back, so
goals, routines, direct runs, sub-workflows and ``llm_agent`` tools all park on the
approval with no change of their own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from zebra.core.models import (
    ProcessDefinition,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.definition_actions import definition_actions

logger = logging.getLogger(__name__)

#: Wrapper process property: what the approval is for and how to start it.
SUPERVISED_LAUNCH_KEY = "__supervised_launch__"
#: Set on a wrapper whose run the owner rejected.
SUPERVISED_REJECTED_KEY = "__supervised_rejected__"
#: Wrapper process property: the markdown the approval form shows.
SUPERVISED_SUMMARY_KEY = "supervised_summary"
#: Wrapper task property: the child process started after approval.
CHILD_KEY = "__supervised_child__"
#: Definition id prefix of the generated wrapper.
WRAPPER_ID_PREFIX = "s:"
#: Name prefix of the generated wrapper; reserved: no adopted workflow may use it.
WRAPPER_NAME_PREFIX = "Supervised run: "
APPROVAL_TASK = "approve_run"
DECISION_RUN = "run"
DECISION_REJECT = "reject"

_FLAGS = {
    "always_irreversible": "irreversible",
    "context_dependent": "may be irreversible",
}


@dataclass(frozen=True)
class SupervisedLaunch:
    """``check_launch``'s answer for a workflow that needs approval before it runs."""

    workflow: str
    actions: list[dict[str, Any]] = field(default_factory=list)


def commons_stop_reason_from(service: Any) -> Any:
    """The awaitable stop reason of a ``__commons__`` service, or None without one."""
    getter = getattr(service, "stop_reason", None)
    return getter() if callable(getter) else None


async def commons_stop_reason(extras: dict[str, Any]) -> str | None:
    """Why Commons activity is stopped (Commons off, kill switch), or None.

    Reads the ``__commons__`` service the web app puts in ``context.extras``; without
    one (CLI, tests) nothing is stopped.
    """
    pending = commons_stop_reason_from(extras.get("__commons__"))
    if pending is None:
        return None
    try:
        reason = await pending
    except Exception as e:  # noqa: BLE001 - an unreadable switch stops the Commons
        logger.warning("Could not read the Commons stop state: %s", e)
        return f"the Commons stop state could not be read ({e})"
    return str(reason) if reason else None


def workflow_actions(definition: ProcessDefinition, registry: Any) -> list[dict[str, Any]]:
    """Every action *definition* runs, with its reversibility hint and an approval flag.

    Includes task and process-level ``construct_action`` / ``destruct_action``: the
    engine runs them too, so the owner must see them.
    """
    actions = []
    for defined in definition_actions(definition):
        hint = "unregistered"
        if registry is not None and registry.has_action(defined.action):
            hint = getattr(
                registry.get_action_class(defined.action), "reversibility_hint", None
            ) or ("context_dependent")
        actions.append(
            {
                "task": defined.label,
                "action": defined.action,
                "hint": hint,
                "flag": _FLAGS.get(hint, "" if hint == "always_reversible" else "unknown"),
            }
        )
    return actions


def is_reserved_name(name: str | None) -> bool:
    """Whether *name* looks like a generated *Supervised run* wrapper's name.

    Such names are reserved: an adopted workflow named like a wrapper would confuse the
    owner's task list and run history, so the import judge and the library refuse it.
    """
    if not isinstance(name, str):
        return False
    return " ".join(name.split()).casefold().startswith(WRAPPER_NAME_PREFIX.strip().casefold())


def supervision_for(definition: ProcessDefinition, extras: dict[str, Any]) -> bool:
    """Whether the library marks *definition*'s workflow ``supervised``.

    Asks the ``__workflow_library__`` in *extras* by name; a workflow the library does
    not hold (an inline sub-workflow, a gym candidate) is not supervised. No name is
    exempt: the generated wrapper is never in the library and never passes through
    ``check_launch`` (``create_library_process`` creates it directly), so a publisher
    cannot dodge supervision by naming a workflow like the wrapper.
    """
    library = extras.get("__workflow_library__")
    checker = getattr(library, "is_supervised", None)
    if not callable(checker):
        return False
    try:
        return checker(definition.name) is True
    except Exception as e:  # noqa: BLE001 - unreadable provenance fails closed
        logger.warning("Could not read supervision of %r (%s): supervising", definition.name, e)
        return True


def approval_summary(
    workflow: str, actions: list[dict[str, Any]], entry: str, properties: dict[str, Any]
) -> str:
    """The markdown the owner reads before approving a supervised run."""
    lines = [
        f"**{workflow}** was imported from another Zebra. Until it has a few approved "
        "runs, I ask you before each one.",
        "",
        f"- Started by: {entry.replace('_', ' ')}",
    ]
    goal = properties.get("goal")
    if isinstance(goal, str) and goal.strip():
        lines.append(f"- Goal: {goal.strip()[:500]}")
    lines += ["", "**What it will do**", ""]
    for a in actions:
        flag = f" — **{a['flag']}**" if a.get("flag") else ""
        lines.append(f"- {a['task']}: `{a['action']}`{flag}")
    if not actions:
        lines.append("- (no actions)")
    return "\n".join(lines)


def supervised_run_definition(real: ProcessDefinition) -> ProcessDefinition:
    """The generated *Supervised run* wrapper for library workflow *real*.

    Not a library workflow: it is never selected, optimized or exported, and the
    imported YAML is untouched. It keeps *real*'s ``result_key``, so callers read the
    output as if *real* had run.
    """
    properties: dict[str, Any] = {}
    if (real.properties or {}).get("result_key"):
        properties["result_key"] = real.properties["result_key"]
    approval = TaskDefinition(
        id=APPROVAL_TASK,
        name=f"Run imported workflow {real.name} for this goal?",
        auto=False,
        properties={
            "owner_only": True,
            "show_prior_outputs": False,
            "schema": {
                "type": "object",
                "title": f"Run imported workflow {real.name}?",
                "description": "Only the Commons owner can answer.",
                "required": ["decision"],
                "properties": {
                    "summary": {
                        "type": "string",
                        "title": "What it will do",
                        "readOnly": True,
                        "default": "{{" + SUPERVISED_SUMMARY_KEY + "}}",
                    },
                    "decision": {
                        "type": "string",
                        "title": "Decision",
                        "enum": [DECISION_RUN, DECISION_REJECT],
                    },
                    "note": {"type": "string", "title": "Note", "format": "multiline"},
                },
            },
        },
    )
    apply = TaskDefinition(
        id="apply_decision",
        name="Run or Refuse",
        action="commons_supervised_run",
        properties={"idempotent": True},
    )
    return ProcessDefinition(
        id=f"{WRAPPER_ID_PREFIX}{real.id}",
        name=f"{WRAPPER_NAME_PREFIX}{real.name}",
        version=real.version,
        first_task_id=APPROVAL_TASK,
        tasks={APPROVAL_TASK: approval, "apply_decision": apply},
        routings=[
            RoutingDefinition(
                id="approve_run_to_apply_decision_0",
                source_task_id=APPROVAL_TASK,
                dest_task_id="apply_decision",
            )
        ],
        properties=properties,
    )


def wrapper_properties(
    real: ProcessDefinition,
    launch: SupervisedLaunch,
    *,
    entry: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """The wrapper process's properties: the caller's, plus what to start on approval."""
    return {
        **properties,
        SUPERVISED_LAUNCH_KEY: {
            "workflow": launch.workflow,
            "definition_id": real.id,
            "entry": entry,
            "actions": launch.actions,
            "properties": properties,
        },
        SUPERVISED_SUMMARY_KEY: approval_summary(
            launch.workflow, launch.actions, entry, properties
        ),
    }


def is_supervised_wrapper(process: Any) -> bool:
    """Whether *process* is a *Supervised run* wrapper."""
    return isinstance((getattr(process, "properties", None) or {}).get(SUPERVISED_LAUNCH_KEY), dict)


class CommonsSupervisedRunAction(TaskAction):
    """Start an approved supervised workflow, or refuse it (``commons_supervised_run``)."""

    description = (
        "After the owner's pre-run approval, run the supervised (imported) workflow as a "
        "child and pass its result on; refuse it when rejected."
    )
    # Starts the approved workflow: whatever it does happens outside this run.
    reversibility_hint = "context_dependent"

    inputs = [
        ParameterDef(
            name="approval_task",
            type="string",
            description="Human approval task whose output holds the decision",
            required=False,
            default=APPROVAL_TASK,
        ),
    ]
    outputs = [
        ParameterDef(name="workflow", type="string", description="The workflow", required=True),
        ParameterDef(name="success", type="bool", description="It ran and finished", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Start the child on approval; on resume pass its result on."""
        launch = context.process.properties.get(SUPERVISED_LAUNCH_KEY)
        if not isinstance(launch, dict):
            return TaskResult.fail("Not a supervised run: no launch record")
        workflow = str(launch.get("workflow") or "")
        if context.subflow_results is not None:
            return await self._finish(task, context, workflow)

        approval = task.properties.get("approval_task", APPROVAL_TASK)
        answer = context.process.properties.get(f"__task_output_{approval}")
        decision = answer.get("decision") if isinstance(answer, dict) else None
        if decision != DECISION_RUN:
            return self._reject(context, workflow, "the owner did not approve the run")
        stopped = await commons_stop_reason(context.extras)
        if stopped:
            return self._reject(context, workflow, f"the Commons is stopped: {stopped}")

        child_id = task.properties.get(CHILD_KEY)
        if not child_id:
            definition = await context.store.load_definition(str(launch.get("definition_id")))
            if definition is None:
                return TaskResult.fail(f"Supervised workflow {workflow!r} definition is missing")
            child = await context.engine.create_process(  # approved at the choke point
                definition,
                properties=dict(launch.get("properties") or {}),
                parent_process_id=context.process.id,
                parent_task_id=task.id,
            )
            child_id = child.id
            task.properties[CHILD_KEY] = child_id
            await context.store.save_task(task)
            logger.info("Supervised run of %r approved: child %s", workflow, child_id)
            start_ids = launch.get("start_task_ids")
            if start_ids:  # a retried goal resumes where it stopped (#187)
                await context.engine.start_process(child_id, start_task_ids=list(start_ids))
            # Otherwise left CREATED: the engine starts it once this task has suspended.
        return TaskResult.suspend([child_id])

    async def _finish(
        self, task: TaskInstance, context: ExecutionContext, workflow: str
    ) -> TaskResult:
        entry = context.subflow_results[0]
        props = entry.get("properties") or {}
        for key, value in props.items():
            if not key.startswith("__") or key == "__output__":
                context.set_process_property(key, value)
        for key in ("__total_cost__", "__total_tokens__"):
            spent = props.get(key) or 0
            if spent:
                context.set_process_property(key, context.get_process_property(key, 0) + spent)
        if not entry.get("success"):
            return TaskResult.fail(entry.get("error") or f"{workflow} failed")
        library = context.extras.get("__workflow_library__")
        state = {"supervised": True, "runs": None}
        recorder = getattr(library, "record_supervised_run", None)
        if callable(recorder):
            try:
                state = recorder(workflow)
            except Exception as e:  # noqa: BLE001 - the run itself succeeded
                logger.warning("Could not count the supervised run of %r: %s", workflow, e)
        return TaskResult.ok(output={"workflow": workflow, "success": True, **state})

    @staticmethod
    def _reject(context: ExecutionContext, workflow: str, why: str) -> TaskResult:
        logger.info("Supervised run of %r refused: %s", workflow, why)
        context.set_process_property(SUPERVISED_REJECTED_KEY, {"workflow": workflow, "reason": why})
        return TaskResult.fail(f"Supervised run of {workflow!r} refused: {why}")

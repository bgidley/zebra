"""RunGoldenGymAction - score workflows on golden tasks and gate self-modifications (#171).

The gym runs curated golden tasks (``WorkflowLibrary.list_golden_tasks``) as child
processes, has an LLM judge score each output against the task's criteria, and
records the scores in the ``MetricsStore``.

With ``candidates`` (staged workflow modifications from ``workflow_optimizer``
with ``gym_gate: true``) it is a promotion gate: each candidate and the current
version run on the workflow's golden tasks, and the candidate is saved only if
its mean score is not more than ``tolerance`` below the current version's. The
gate fails closed: a gated candidate that cannot be run safely or scored is
rejected. Without candidates it scores the current version of every workflow
that has golden tasks (on demand).

The children start together and the task suspends on them (``TaskResult.suspend``);
the engine re-runs the action with ``context.subflow_results`` once they finish.
The action never fails its process.
"""

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from zebra.core.models import ProcessDefinition, ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction
from zebra_agent.metrics import GymScore

from zebra_tasks.agent.execute_workflow import extract_workflow_output
from zebra_tasks.agent.optimizer import save_workflow_file
from zebra_tasks.agent.stuck import _parse_json
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm
from zebra_tasks.subtasks.common import start_child

logger = logging.getLogger(__name__)

#: Task property holding the gym plan across the suspend.
PLAN_KEY = "__gym_plan__"
#: Task property mapping each child process id to its run.
RUNS_KEY = "__gym_runs__"
#: Process property marking a gym child (not a user goal).
GYM_CHILD_KEY = "__gym_run__"

CURRENT = "current"
CANDIDATE = "candidate"
PROMOTED = "promoted"
REJECTED = "rejected"

_PURE_TEMPLATE_RE = re.compile(r"^\{\{\s*([\w.]+)\s*\}\}$")

_MAX_OUTPUT_CHARS = 6000
_MAX_EXCERPT_CHARS = 500

JUDGE_SYSTEM_PROMPT = """You grade the output of an AI workflow against a golden task.

You get the goal the workflow was given, the expected outcome, a numbered list of
criteria and the workflow's output. Score each criterion:
- 1: fully met
- 0.5: partly met
- 0: not met, or the output is missing, empty or off-topic

Judge only the output against the criteria. Be strict and consistent: the same
output must always get the same scores.

Return only a JSON object:
{"criteria": [{"criterion": 1, "score": 1, "note": "short reason"}, ...],
 "reasoning": "one or two sentences"}
with exactly one entry per criterion, in order."""

JUDGE_USER_PROMPT = """## Goal
{goal}

## Expected outcome
{expected}

## Criteria
{criteria}

## Workflow output
{output}"""


class RunGoldenGymAction(TaskAction):
    """Score workflows on golden tasks; promote or reject staged modifications."""

    description = (
        "Run golden tasks against workflows, score the outputs with an LLM judge and "
        "record the scores. With candidates, promote each staged workflow modification "
        "only if it scores no worse than the current version (fails closed)."
    )

    inputs = [
        ParameterDef(
            name="candidates",
            type="list[dict]",
            description=(
                "Staged modifications ({name, original_yaml, modified_yaml, ...}), e.g. "
                "'{{optimization_results.pending_gym}}'. Omit to score current workflows."
            ),
            required=False,
        ),
        ParameterDef(
            name="workflows",
            type="list[string]",
            description="On demand: only score these workflows (default: all with golden tasks)",
            required=False,
        ),
        ParameterDef(
            name="promote",
            type="bool",
            description="Save promoted candidates (false = check only)",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="tolerance",
            type="float",
            description="Reject a candidate scoring more than this below the current version",
            required=False,
            default=0.1,
        ),
        ParameterDef(
            name="timeout",
            type="float",
            description="Seconds each golden-task run's inline auto-task chain may take",
            required=False,
            default=150,
        ),
        ParameterDef(
            name="max_tasks_per_workflow",
            type="int",
            description="Golden tasks used per workflow",
            required=False,
            default=3,
        ),
        ParameterDef(
            name="max_runs",
            type="int",
            description="Workflow runs per gym; a candidate over the cap is rejected",
            required=False,
            default=12,
        ),
        ParameterDef(
            name="model",
            type="string",
            description="Judge model",
            required=False,
            default="medium",
        ),
        ParameterDef(
            name="results_key",
            type="string",
            description="Optimizer results property to update with the gate's verdicts",
            required=False,
            default="optimization_results",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the gym report",
            required=False,
            default="golden_gym",
        ),
    ]

    outputs = [
        ParameterDef(
            name="decisions",
            type="list[dict]",
            description="Per candidate: workflow, decision (promoted/rejected), reason, means",
            required=True,
        ),
        ParameterDef(
            name="scores",
            type="list[dict]",
            description="Per run: golden_id, workflow, variant, score, error",
            required=True,
        ),
        ParameterDef(
            name="skipped",
            type="list[dict]",
            description="Golden tasks or workflows not run, with the reason",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Start the golden-task runs, or score them when the children have finished."""
        try:
            if context.subflow_results is not None:
                return await self._finish(task, context)
            return await self._start(task, context)
        except Exception as e:  # noqa: BLE001 - the gym never fails its process
            logger.exception("Golden gym failed")
            plan = task.properties.get(PLAN_KEY) or self._new_plan(task, context)
            for candidate in plan["candidates"]:
                if candidate["status"] == "pending":
                    _decide(candidate, REJECTED, f"gym error: {e}")
            plan["errors"].append(str(e))
            return await self._complete(task, context, plan, [])

    # ------------------------------------------------------------------
    # Start: plan the runs, start the children, suspend
    # ------------------------------------------------------------------

    def _new_plan(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        props = task.properties
        # On demand only without a ``candidates`` property: an unset reference in
        # the Dream Cycle means nothing to gate, not "score everything".
        candidates = None
        if "candidates" in props:
            candidates = _resolve_value(context, props.get("candidates"))
            if not isinstance(candidates, list):
                candidates = []
        elif isinstance(context.process.properties.get("candidates"), list):
            # Golden Gym run inputs: candidates to check (with promote: false).
            candidates = context.process.properties["candidates"]
        promote = props.get("promote", True)
        if isinstance(promote, str):
            promote = promote.strip().lower() not in ("false", "0", "no", "")
        return {
            "mode": "gate" if candidates is not None else "on_demand",
            "promote": bool(promote),
            "candidates": [
                {
                    "name": c.get("name"),
                    "original_yaml": c.get("original_yaml"),
                    "modified_yaml": c.get("modified_yaml"),
                    "llm_defined": bool(c.get("llm_defined", True)),
                    "reason": c.get("reason", ""),
                    "change": c.get("change") or {"type": "modify", "workflow": c.get("name")},
                    "status": "pending",
                }
                for c in (candidates or [])
                if isinstance(c, dict)
            ],
            "skipped": [],
            "errors": [],
        }

    async def _start(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        plan = self._new_plan(task, context)
        props = task.properties
        library = context.extras.get("__workflow_library__")
        golden = library.list_golden_tasks() if library is not None else []
        if library is None:
            logger.warning("Golden gym: no workflow library, so no golden tasks")
        max_tasks = int(props.get("max_tasks_per_workflow", 3))
        max_runs = int(props.get("max_runs", 12))
        registry = context.engine.actions
        runs: list[dict[str, Any]] = []  # each: golden task, variant, definition, candidate

        def tasks_for(workflow: str) -> list:
            return [t for t in golden if t.workflow == workflow][:max_tasks]

        if plan["mode"] == "gate":
            for index, candidate in enumerate(plan["candidates"]):
                name = candidate["name"]
                golden_tasks = tasks_for(name)
                if not golden_tasks:
                    _decide(candidate, PROMOTED, "ungated: no golden tasks")
                    continue
                candidate["golden_ids"] = [t.id for t in golden_tasks]
                if not candidate["original_yaml"]:
                    try:
                        candidate["original_yaml"] = library.get_workflow_yaml(name)
                    except ValueError:
                        pass
                try:
                    current = load_definition_from_yaml(candidate["original_yaml"] or "")
                    modified = load_definition_from_yaml(candidate["modified_yaml"] or "")
                except Exception as e:  # noqa: BLE001
                    _decide(candidate, REJECTED, f"gym could not load the workflow: {e}")
                    continue
                problem = unsafe_reason(modified, registry) or unsafe_reason(current, registry)
                if problem:
                    _decide(candidate, REJECTED, f"gym cannot run it safely: {problem}")
                    continue
                if len(runs) + 2 * len(golden_tasks) > max_runs:
                    _decide(candidate, REJECTED, f"gym run cap ({max_runs}) reached")
                    continue
                # The candidate keeps its name and version, so give it its own
                # definition id: otherwise saving it would replace the current one.
                modified = modified.model_copy(
                    update={"id": f"{modified.id}-gym-{uuid.uuid4().hex[:8]}"}
                )
                for golden_task in golden_tasks:
                    runs.append(_run(golden_task, CURRENT, current, index))
                    runs.append(_run(golden_task, CANDIDATE, modified, index))
        else:
            active = {w.name for w in await library.list_workflows()} if library else set()
            wanted = _resolve_value(context, props.get("workflows"))
            if not isinstance(wanted, list):
                wanted = context.process.properties.get("workflows")
            if not isinstance(wanted, list) or not wanted:
                wanted = sorted({t.workflow for t in golden})
            for name in wanted:
                golden_tasks = tasks_for(name)
                if name not in active or not golden_tasks:
                    plan["skipped"].append(
                        {"workflow": name, "reason": "not in the library or no golden tasks"}
                    )
                    continue
                definition = library.get_workflow(name)
                problem = unsafe_reason(definition, registry)
                if problem:
                    plan["skipped"].append({"workflow": name, "reason": problem})
                    continue
                for golden_task in golden_tasks:
                    if len(runs) >= max_runs:
                        plan["skipped"].append(
                            {"golden_id": golden_task.id, "reason": f"run cap ({max_runs})"}
                        )
                        continue
                    runs.append(_run(golden_task, CURRENT, definition, None))

        if not runs:
            return await self._complete(task, context, plan, [])

        if self._judge_provider(task, context) is None:
            for candidate in plan["candidates"]:
                if candidate["status"] == "pending":
                    _decide(candidate, REJECTED, "gym has no LLM judge")
            plan["errors"].append("no LLM provider for the judge")
            return await self._complete(task, context, plan, [])

        child_ids = await self._create_children(task, context, runs)
        task.properties[PLAN_KEY] = plan
        task.properties[RUNS_KEY] = {
            pid: {k: v for k, v in run.items() if k != "definition"}
            for pid, run in zip(child_ids, runs, strict=True)
        }
        await context.store.save_task(task)

        timeout = props.get("timeout", 150)
        started = await asyncio.gather(
            *(start_child(context, pid, timeout) for pid in child_ids), return_exceptions=True
        )
        for pid, outcome in zip(child_ids, started, strict=True):
            if isinstance(outcome, BaseException):
                await self._fail_unfinished(context, pid, outcome)
        return TaskResult.suspend(child_ids)

    async def _create_children(
        self, task: TaskInstance, context: ExecutionContext, runs: list[dict[str, Any]]
    ) -> list[str]:
        parent = context.process.properties
        child_ids = []
        for run in runs:
            properties = {
                "goal": run["goal"],
                "__parent_process_id__": context.process.id,
                "__parent_task_id__": task.id,
                GYM_CHILD_KEY: True,
            }
            if parent.get("__llm_model__"):
                properties["__llm_model__"] = parent["__llm_model__"]
            child = await context.engine.create_process(
                run["definition"],
                properties=properties,
                parent_process_id=context.process.id,
                parent_task_id=task.id,
            )
            child_ids.append(child.id)
        return child_ids

    async def _fail_unfinished(
        self, context: ExecutionContext, process_id: str, error: BaseException
    ) -> None:
        """Fail a child whose start raised, so the suspend can still resume."""
        logger.warning("Golden gym run %s did not start cleanly: %s", process_id, error)
        process = await context.store.load_process(process_id)
        if process is not None and process.state not in (
            ProcessState.COMPLETE,
            ProcessState.FAILED,
        ):
            await context.engine.fail_process(process_id, f"Gym run failed to start: {error}")

    # ------------------------------------------------------------------
    # Finish: judge the outputs, decide, record
    # ------------------------------------------------------------------

    async def _finish(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        plan = task.properties.get(PLAN_KEY) or self._new_plan(task, context)
        runs = task.properties.get(RUNS_KEY) or {}
        library = context.extras.get("__workflow_library__")
        golden = {t.id: t for t in (library.list_golden_tasks() if library else [])}
        provider = self._judge_provider(task, context)

        async def score(entry: dict[str, Any]) -> dict[str, Any]:
            run = dict(runs.get(entry["process_id"]) or {})
            properties = entry.get("properties") or {}
            _add_child_cost(context, properties)
            run.update(score=None, error=None, details={})
            if not entry.get("success"):
                run.update(score=0.0, error=entry.get("error") or "workflow run failed")
                return run
            output = extract_workflow_output(properties, run.get("result_key"))
            run["details"]["output_excerpt"] = _text(output)[:_MAX_EXCERPT_CHARS]
            golden_task = golden.get(run.get("golden_id"))
            if golden_task is None:
                run["error"] = "golden task no longer exists"
            elif provider is None:
                run["error"] = "no LLM judge"
            else:
                await self._judge(context, provider, golden_task, output, run)
            return run

        scored = await asyncio.gather(*(score(entry) for entry in context.subflow_results))
        return await self._complete(task, context, plan, list(scored))

    async def _judge(
        self,
        context: ExecutionContext,
        provider: Any,
        golden_task: Any,
        output: Any,
        run: dict[str, Any],
    ) -> None:
        """Score *output* against the golden task's criteria into *run* (score, details)."""
        criteria = golden_task.criteria
        try:
            response = await provider.complete(
                messages=[
                    Message.system(JUDGE_SYSTEM_PROMPT),
                    Message.user(
                        JUDGE_USER_PROMPT.format(
                            goal=golden_task.goal,
                            expected=golden_task.expected,
                            criteria="\n".join(f"{i}. {c}" for i, c in enumerate(criteria, 1)),
                            output=_text(output)[:_MAX_OUTPUT_CHARS] or "(no output)",
                        )
                    ),
                ],
                temperature=0.0,
                max_tokens=800,
            )
            verdict = _parse_json(response.content or "")
            scores = [float(c["score"]) for c in verdict["criteria"]]
            if len(scores) != len(criteria):
                raise ValueError(f"{len(scores)} scores for {len(criteria)} criteria")
        except Exception as e:  # noqa: BLE001 - an unscored run fails the gate closed
            logger.warning("Golden gym judge failed for %s: %s", golden_task.id, e)
            run["error"] = f"judge failed: {e}"
            return
        scores = [min(max(s, 0.0), 1.0) for s in scores]
        run["score"] = round(sum(scores) / len(scores), 3)
        run["details"]["criteria"] = [
            {"criterion": c, "score": s, "note": str(v.get("note", ""))[:200]}
            for c, s, v in zip(criteria, scores, verdict["criteria"], strict=True)
        ]
        run["details"]["reasoning"] = str(verdict.get("reasoning", ""))[:500]

    async def _complete(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        plan: dict[str, Any],
        scored: list[dict[str, Any]],
    ) -> TaskResult:
        """Decide the pending candidates, save promotions, record scores and report."""
        tolerance = float(task.properties.get("tolerance", 0.1))
        for index, candidate in enumerate(plan["candidates"]):
            if candidate["status"] == "pending":
                mine = [r for r in scored if r.get("candidate_index") == index]
                _decide_on_scores(candidate, mine, tolerance)

        library_path = task.properties.get("workflow_library_path") or (
            context.process.properties.get("__workflow_library_path__")
        )
        for candidate in plan["candidates"]:
            if candidate["status"] != PROMOTED or not plan["promote"]:
                continue
            if not library_path:
                _decide(candidate, REJECTED, "no library path to save to")
                continue
            save_workflow_file(
                library_path,
                candidate["name"],
                candidate["modified_yaml"],
                llm_defined=candidate["llm_defined"],
            )

        decisions = {
            index: candidate["status"] for index, candidate in enumerate(plan["candidates"])
        }
        records = [
            GymScore.create(
                gym_run_id=context.process.id,
                golden_id=run["golden_id"],
                workflow_name=run["workflow"],
                variant=run["variant"],
                score=run["score"],
                error=run["error"],
                details={
                    **run["details"],
                    "mode": plan["mode"],
                    **(
                        {"decision": decisions[run["candidate_index"]]}
                        if run.get("candidate_index") is not None
                        else {}
                    ),
                },
            )
            for run in scored
        ]
        report = {
            "mode": plan["mode"],
            "promote": plan["promote"],
            "decisions": [_decision_report(c) for c in plan["candidates"]],
            "scores": [
                {k: run.get(k) for k in ("golden_id", "workflow", "variant", "score", "error")}
                for run in scored
            ],
            "skipped": plan["skipped"],
            "errors": plan["errors"],
        }
        context.set_process_property(
            task.properties.get("output_key", "golden_gym"),
            report,
        )
        if plan["mode"] == "gate" and plan["promote"]:
            self._update_optimizer_results(task, context, plan["candidates"])
        await _record_scores(context, records, report)
        return TaskResult.ok(output=report)

    def _update_optimizer_results(
        self, task: TaskInstance, context: ExecutionContext, candidates: list[dict[str, Any]]
    ) -> None:
        """Move each gated modification into changes_made or failed_changes (#128 shape)."""
        key = task.properties.get("results_key", "optimization_results")
        results = context.get_process_property(key)
        if not isinstance(results, dict):
            return
        results = json.loads(json.dumps(results))  # copy; properties are JSON
        for candidate in candidates:
            name = candidate["name"]
            if candidate["status"] == PROMOTED:
                results.setdefault("changes_made", []).append(candidate["change"])
                results.setdefault("modified_workflows", []).append(
                    {
                        "name": name,
                        "original_yaml": candidate["original_yaml"],
                        "modified_yaml": candidate["modified_yaml"],
                        "reason": candidate["reason"],
                    }
                )
            else:
                results.setdefault("failed_changes", []).append(
                    {"type": "modify", "workflow": name, "reason": candidate["decision_reason"]}
                )
            for change in results.get("continuation_changes", []):
                if change.get("workflow") == name and change.get("status") == "pending_gym":
                    change["status"] = "made" if candidate["status"] == PROMOTED else "failed"
                    change["reason"] = candidate["decision_reason"]
        results["pending_gym"] = []
        context.set_process_property(key, results)

    def _judge_provider(self, task: TaskInstance, context: ExecutionContext) -> Any:
        try:
            return get_llm(task.properties.get("model") or "medium", context)
        except Exception as e:  # noqa: BLE001
            logger.warning("Golden gym: no judge provider: %s", e)
            return None


def unsafe_reason(definition: ProcessDefinition, registry: Any) -> str | None:
    """Return why the gym must not run *definition*, or None if it is safe to run.

    The gym only runs workflows that finish on their own and cannot do anything
    irreversible: every task is ``auto``, and every action is registered and not
    ``always_irreversible``.
    """
    for task_id, task_def in definition.tasks.items():
        if not task_def.auto:
            return f"task '{task_id}' needs a human"
        if not task_def.action:
            continue
        if registry is None or not registry.has_action(task_def.action):
            return f"action '{task_def.action}' is not registered"
        hint = getattr(registry.get_action_class(task_def.action), "reversibility_hint", None)
        if hint == "always_irreversible":
            return f"action '{task_def.action}' is irreversible"
    return None


def _run(golden_task: Any, variant: str, definition: Any, index: int | None) -> dict[str, Any]:
    return {
        "golden_id": golden_task.id,
        "workflow": golden_task.workflow,
        "goal": golden_task.goal,
        "variant": variant,
        "candidate_index": index,
        "result_key": (definition.properties or {}).get("result_key"),
        "definition": definition,
    }


def _resolve_value(context: ExecutionContext, raw: Any) -> Any:
    """Resolve a pure ``{{a.b}}`` template to the property's native value.

    Anything else is returned unchanged; an unset reference resolves to None.
    """
    if not isinstance(raw, str):
        return raw
    match = _PURE_TEMPLATE_RE.match(raw.strip())
    if not match:
        return raw
    root, *rest = match.group(1).split(".")
    value: Any = context.process.properties.get(root)
    for part in rest:
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _decide(candidate: dict[str, Any], status: str, reason: str) -> None:
    candidate["status"] = status
    candidate["decision_reason"] = reason


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _decide_on_scores(
    candidate: dict[str, Any], runs: list[dict[str, Any]], tolerance: float
) -> None:
    """Promote *candidate* unless it scores more than *tolerance* below the current version."""
    by_variant = {v: [r for r in runs if r["variant"] == v] for v in (CURRENT, CANDIDATE)}
    expected = len(candidate.get("golden_ids") or [])
    if not expected or any(len(by_variant[v]) != expected for v in by_variant):
        _decide(candidate, REJECTED, "gym runs missing")
        return
    if any(r["score"] is None for r in runs):
        errors = "; ".join(sorted({r["error"] for r in runs if r["score"] is None}))
        _decide(candidate, REJECTED, f"gym could not score it: {errors}")
        return
    current = _mean([r["score"] for r in by_variant[CURRENT]])
    modified = _mean([r["score"] for r in by_variant[CANDIDATE]])
    candidate["current_mean"] = current
    candidate["candidate_mean"] = modified
    candidate["per_task"] = [
        {
            "golden_id": golden_id,
            CURRENT: next(r["score"] for r in by_variant[CURRENT] if r["golden_id"] == golden_id),
            CANDIDATE: next(
                r["score"] for r in by_variant[CANDIDATE] if r["golden_id"] == golden_id
            ),
        }
        for golden_id in candidate["golden_ids"]
    ]
    if modified < current - tolerance:
        _decide(
            candidate,
            REJECTED,
            f"gym regression: candidate scored {modified:.2f} vs current {current:.2f}",
        )
    else:
        _decide(
            candidate,
            PROMOTED,
            f"gym passed: candidate scored {modified:.2f} vs current {current:.2f}",
        )


def _decision_report(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow": candidate["name"],
        "decision": candidate["status"],
        "reason": candidate.get("decision_reason", ""),
        "current_mean": candidate.get("current_mean"),
        "candidate_mean": candidate.get("candidate_mean"),
        "per_task": candidate.get("per_task", []),
    }


def _add_child_cost(context: ExecutionContext, child_properties: dict[str, Any]) -> None:
    """Add a gym run's LLM spend to this process."""
    for key in ("__total_cost__", "__total_tokens__"):
        spent = child_properties.get(key) or 0
        if spent:
            context.set_process_property(key, context.get_process_property(key, 0) + spent)


def _text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False, default=str)


async def _record_scores(
    context: ExecutionContext, records: list[GymScore], report: dict[str, Any]
) -> None:
    """Store the scores; a missing or failing store is reported, never raised."""
    if not records:
        return
    store = context.extras.get("__metrics_store__")
    if store is None:
        logger.warning("Golden gym: no metrics store, scores not kept")
        report["errors"].append("no metrics store: scores not kept")
        return
    try:
        await store.record_gym_scores(records)
    except Exception as e:  # noqa: BLE001
        logger.warning("Golden gym: could not store scores: %s", e)
        report["errors"].append(f"scores not stored: {e}")

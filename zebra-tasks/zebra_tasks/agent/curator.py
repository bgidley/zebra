"""WorkflowCuratorAction - retire failing, unused, duplicate and broken workflows (#148).

Runs in the Dream Cycle before the workflows are loaded for evaluation, so the
evaluator and optimizer only see the active library. Retiring is soft: the
``WorkflowLibrary`` moves the YAML to ``retired/``, where it stays loadable by
name for run history and continuations, and can be restored from the web UI.
"""

import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml, validate_definition
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.load_definitions import SYSTEM_WORKFLOW_NAMES
from zebra_tasks.llm.base import Message

logger = logging.getLogger(__name__)

SYSTEM_TAG = "system"
LLM_DEFINED_TAG = "llm-defined"

# Rules in the order they are applied; the per-cycle cap keeps the earliest.
BROKEN = "broken"
SUPERSEDED_COPY = "superseded_copy"
FAILING = "failing"
UNUSED = "unused"
DUPLICATE = "duplicate"

# name: (env var, default)
_SETTINGS: dict[str, tuple[str, Any]] = {
    "min_runs": ("ZEBRA_CURATOR_MIN_RUNS", 5),
    "min_success_rate": ("ZEBRA_CURATOR_MIN_SUCCESS_RATE", 0.3),
    "unused_days": ("ZEBRA_CURATOR_UNUSED_DAYS", 30),
    "max_retire": ("ZEBRA_CURATOR_MAX_RETIRE_PER_CYCLE", 5),
    "dry_run": ("ZEBRA_CURATOR_DRY_RUN", False),
    "detect_duplicates": ("ZEBRA_CURATOR_DETECT_DUPLICATES", True),
}

DUPLICATE_SYSTEM_PROMPT = """You review an AI agent's workflow library for duplicates.

Two workflows are duplicates when they serve the same purpose for the same kind of
goal, so the agent would never need both. Workflows that merely share a topic, or
that do related but distinct jobs, are NOT duplicates. When unsure, say they are not.

Respond with JSON only:
{"duplicates": [{"a": "workflow name", "b": "workflow name", "reason": "why"}]}
Use the exact workflow names given. Return {"duplicates": []} if there are none."""


def _setting(task: TaskInstance, name: str) -> Any:
    """Resolve a setting: task property > ``ZEBRA_CURATOR_*`` env var > default."""
    env_var, default = _SETTINGS[name]
    raw = task.properties.get(name)
    if raw is None:
        raw = os.environ.get(env_var)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes")
    return type(default)(raw)


class WorkflowCuratorAction(TaskAction):
    """
    Retire workflows that are broken, superseded, failing, unused or duplicated.

    Rules, in priority order:
        - broken: the definition no longer loads or validates (any workflow)
        - superseded_copy: an older file with the same name as a newer one
          (the optimizer saves modified workflows as ``foo_1.yaml``)
        - failing: ``total_runs >= min_runs`` and ``success_rate < min_success_rate``
        - unused: ``llm-defined`` only — not run (or, never run, not created)
          within ``unused_days``
        - duplicate: an LLM judges two workflows to do the same job; the weaker
          (lower success rate, then fewer runs) is retired if it is ``llm-defined``

    Workflows tagged ``system`` and the core system workflows are never touched.
    Hand-written workflows are only retired when broken or failing. At most
    ``max_retire`` workflows are retired per cycle; the rest are reported as
    deferred. ``dry_run`` reports decisions without retiring anything.

    Settings come from task properties, then ``ZEBRA_CURATOR_*`` env vars, then
    defaults (see ``_SETTINGS``).

    Store access: ``__workflow_library__`` (required) and ``__metrics_store__``
    (optional — without it the failing rule is skipped and unused falls back to
    file age) from ``context.extras``.

    Example workflow usage:
        ```yaml
        tasks:
          curate_workflows:
            name: "Retire Stale Workflows"
            action: workflow_curator
            auto: true
            properties:
              output_key: curation
        ```
    """

    description = "Retire failing, unused, duplicate and broken workflows from the library."
    reversibility_hint = "always_reversible"  # retired workflows can be restored

    inputs = [
        ParameterDef(
            name="min_runs",
            type="int",
            description="Runs needed before the failing rule applies (default 5)",
            required=False,
            default=5,
        ),
        ParameterDef(
            name="min_success_rate",
            type="float",
            description="Success rate below which a workflow is failing (default 0.3)",
            required=False,
            default=0.3,
        ),
        ParameterDef(
            name="unused_days",
            type="int",
            description="Days without a run before an llm-defined workflow is unused (30)",
            required=False,
            default=30,
        ),
        ParameterDef(
            name="max_retire",
            type="int",
            description="Maximum workflows retired per cycle (default 5)",
            required=False,
            default=5,
        ),
        ParameterDef(
            name="dry_run",
            type="bool",
            description="Report decisions without retiring anything",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="detect_duplicates",
            type="bool",
            description="Ask the LLM to find duplicate workflows (default true)",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the curation report",
            required=False,
            default="curation",
        ),
    ]

    outputs = [
        ParameterDef(
            name="retired",
            type="list[dict]",
            description="Decisions applied (or, in dry run, that would be applied)",
            required=True,
        ),
        ParameterDef(
            name="deferred",
            type="list[dict]",
            description="Decisions held back by the per-cycle cap",
            required=True,
        ),
        ParameterDef(
            name="dry_run",
            type="bool",
            description="Whether this was a dry run",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Decide which workflows to retire and retire them."""
        output_key = task.properties.get("output_key", "curation")
        library = context.extras.get("__workflow_library__")
        if library is None:
            logger.warning("workflow_curator: no __workflow_library__ in extras; skipping")
            report = {"retired": [], "deferred": [], "dry_run": True, "skipped": "no library"}
            context.set_process_property(output_key, report)
            return TaskResult.ok(output=report)

        dry_run = _setting(task, "dry_run")
        max_retire = _setting(task, "max_retire")

        files = library.list_workflow_files()
        stats = await self._load_stats(context.extras.get("__metrics_store__"))
        decisions = self._rule_decisions(task, files, stats)
        if _setting(task, "detect_duplicates"):
            decisions += await self._duplicate_decisions(task, context, files, stats, decisions)

        paths = [d.pop("_path") for d in decisions]  # keep the report JSON-serializable
        for decision, path in zip(decisions, paths, strict=True):
            decision["file"] = path.name
        to_apply, deferred = decisions[:max_retire], decisions[max_retire:]
        for decision, path in zip(to_apply, paths, strict=False):
            decision["applied"] = False
            if dry_run:
                continue
            try:
                library.retire(
                    decision["workflow"],
                    decision["reason"],
                    superseded_by=decision.get("superseded_by"),
                    path=path,
                )
                decision["applied"] = True
            except Exception as e:
                logger.warning("workflow_curator: could not retire %s: %s", decision["workflow"], e)
                decision["error"] = str(e)

        report = {"retired": to_apply, "deferred": deferred, "dry_run": dry_run}
        logger.info(
            "workflow_curator: %d retired%s, %d deferred",
            len(to_apply),
            " (dry run)" if dry_run else "",
            len(deferred),
        )
        context.set_process_property(output_key, report)
        return TaskResult.ok(output=report)

    @staticmethod
    async def _load_stats(metrics: Any) -> dict[str, Any]:
        """Return workflow name -> WorkflowStats, or {} without a metrics store."""
        if metrics is None:
            logger.warning("workflow_curator: no __metrics_store__; failing rule skipped")
            return {}
        try:
            return {s.workflow_name: s for s in await metrics.get_all_stats()}
        except Exception as e:
            logger.warning("workflow_curator: could not load workflow stats: %s", e)
            return {}

    def _rule_decisions(
        self, task: TaskInstance, files: list[Any], stats: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Apply the deterministic rules; returns decisions in priority order."""
        min_runs = _setting(task, "min_runs")
        min_success_rate = _setting(task, "min_success_rate")
        unused_cutoff = datetime.now(UTC) - timedelta(days=_setting(task, "unused_days"))

        by_rule: dict[str, list[dict[str, Any]]] = {
            BROKEN: [],
            SUPERSEDED_COPY: [],
            FAILING: [],
            UNUSED: [],
        }
        seen: set[str] = set()
        for wf in files:  # newest first, so the first file per name is current
            if _is_protected(wf):
                continue
            ws = stats.get(wf.name)
            if wf.name in seen:
                by_rule[SUPERSEDED_COPY].append(
                    _decision(
                        wf,
                        ws,
                        SUPERSEDED_COPY,
                        "Older copy of a workflow that has a newer version",
                        superseded_by=wf.name,
                    )
                )
                continue
            seen.add(wf.name)

            problem = _definition_problem(wf.content)
            if problem:
                by_rule[BROKEN].append(_decision(wf, ws, BROKEN, f"Invalid definition: {problem}"))
            elif ws and ws.total_runs >= min_runs and ws.success_rate < min_success_rate:
                by_rule[FAILING].append(
                    _decision(
                        wf,
                        ws,
                        FAILING,
                        f"{ws.success_rate:.0%} success over {ws.total_runs} runs "
                        f"(threshold {min_success_rate:.0%})",
                    )
                )
            elif LLM_DEFINED_TAG in wf.tags:
                last_active = (ws.last_used if ws else None) or wf.modified_at
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=UTC)
                if last_active < unused_cutoff:
                    by_rule[UNUSED].append(
                        _decision(
                            wf,
                            ws,
                            UNUSED,
                            f"LLM-defined workflow not used since {last_active.date()}",
                        )
                    )
        return [d for rule in by_rule.values() for d in rule]

    async def _duplicate_decisions(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        files: list[Any],
        stats: dict[str, Any],
        decided: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Ask the LLM for duplicate pairs and retire the weaker llm-defined one."""
        decided_names = {d["workflow"] for d in decided if d["rule"] != SUPERSEDED_COPY}
        current: dict[str, Any] = {}
        for wf in files:
            if wf.name not in current and wf.name not in decided_names and not _is_protected(wf):
                current[wf.name] = wf
        if not any(LLM_DEFINED_TAG in wf.tags for wf in current.values()) or len(current) < 2:
            return []

        provider = _get_provider(task, context)
        if provider is None:
            logger.warning("workflow_curator: no LLM provider; duplicate check skipped")
            return []

        try:
            response = await provider.complete(
                messages=[
                    Message.system(DUPLICATE_SYSTEM_PROMPT),
                    Message.user(_duplicate_prompt(current.values())),
                ],
                temperature=0.0,
                max_tokens=1500,
            )
            _track_cost(context, response, getattr(provider, "model", None))
            pairs = _parse_pairs(response.content or "")
        except Exception as e:
            logger.warning("workflow_curator: duplicate check failed: %s", e)
            return []

        decisions = []
        retiring: set[str] = set()
        for pair in pairs:
            a, b = pair.get("a"), pair.get("b")
            if a not in current or b not in current or a == b or {a, b} & retiring:
                continue
            weaker, stronger = sorted((a, b), key=lambda n: _strength(stats.get(n)))
            if LLM_DEFINED_TAG not in current[weaker].tags:
                continue  # hand-written workflows are never retired as duplicates
            retiring.add(weaker)
            decisions.append(
                _decision(
                    current[weaker],
                    stats.get(weaker),
                    DUPLICATE,
                    f"Duplicate of {stronger!r}: {pair.get('reason', '')}".strip(),
                    superseded_by=stronger,
                )
            )
        return decisions


def _is_protected(wf: Any) -> bool:
    return SYSTEM_TAG in wf.tags or wf.name in SYSTEM_WORKFLOW_NAMES


def _definition_problem(content: str) -> str | None:
    """Return why a workflow definition is unusable, or None if it is valid."""
    try:
        definition = load_definition_from_yaml(content)
    except Exception as e:
        return str(e)
    errors = validate_definition(definition)
    return "; ".join(errors) if errors else None


def _decision(
    wf: Any, ws: Any, rule: str, reason: str, superseded_by: str | None = None
) -> dict[str, Any]:
    return {
        "workflow": wf.name,
        "rule": rule,
        "reason": reason,
        "superseded_by": superseded_by,
        "llm_defined": LLM_DEFINED_TAG in wf.tags,
        "stats": {
            "total_runs": ws.total_runs if ws else 0,
            "success_rate": round(ws.success_rate, 3) if ws else None,
            "last_used": ws.last_used.isoformat() if ws and ws.last_used else None,
        },
        "_path": wf.path,
    }


def _strength(ws: Any) -> tuple[float, int]:
    """Sort key: weaker workflows sort first."""
    if ws is None:
        return (0.0, 0)
    return (ws.success_rate, ws.total_runs)


def _duplicate_prompt(workflows: Any) -> str:
    lines = ["## Workflows\n"]
    for wf in workflows:
        try:
            definition = load_definition_from_yaml(wf.content)
            steps = ", ".join(t.name for t in definition.tasks.values())
        except Exception:
            steps = "?"
        lines.append(f"### {wf.name}")
        lines.append(f"Description: {_yaml_field(wf.content, 'description')}")
        lines.append(f"Use when: {_yaml_field(wf.content, 'use_when')}")
        lines.append(f"Steps: {steps}\n")
    lines.append("Which pairs of these workflows are duplicates?")
    return "\n".join(lines)


def _yaml_field(content: str, key: str) -> str:
    import yaml

    try:
        data = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return ""
    return str(data.get(key) or "")


def _parse_pairs(content: str) -> list[dict[str, Any]]:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        content = match.group(1)
    data = json.loads(content)
    pairs = data.get("duplicates") if isinstance(data, dict) else None
    return [p for p in pairs or [] if isinstance(p, dict)]


def _get_provider(task: TaskInstance, context: ExecutionContext) -> Any:
    """Resolve the LLM provider the same way the other dream-cycle actions do."""
    from zebra_tasks.llm.providers.registry import get_provider

    provider_name = task.properties.get("provider") or context.process.properties.get(
        "__llm_provider_name__"
    )
    model = task.properties.get("model") or context.process.properties.get("__llm_model__")
    if provider_name:
        return get_provider(provider_name, model)
    return context.process.properties.get("__llm_provider__")


def _track_cost(context: ExecutionContext, response: Any, model: str | None) -> None:
    """Add the duplicate check's tokens and cost to the process totals."""
    from zebra_tasks.llm.pricing import calculate_cost

    usage = response.usage
    tokens = context.get_process_property("__total_tokens__", 0)
    context.set_process_property("__total_tokens__", tokens + usage.total_tokens)
    cost = calculate_cost(model or response.model, usage.input_tokens, usage.output_tokens)
    total = context.get_process_property("__total_cost__", 0.0)
    context.set_process_property("__total_cost__", total + cost)

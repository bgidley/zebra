"""Static and run-time checks of workflow output contracts (#271).

``validate_contracts`` reads a ``ProcessDefinition`` and reports ``{{...}}`` references in task
properties that cannot resolve: a reference to a task that does not exist, a ``{{task.output}}``
that no path to the referencing task produces (error), or that only some paths produce
(warning). ``validate_output_schema`` is the small JSON Schema subset used to check structured
``llm_call`` output.
"""

import re
from dataclasses import dataclass
from typing import Any

from zebra.core.models import ProcessDefinition

# Same grammar as ExecutionContext.resolve_template
TEMPLATE_REF = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")

# Roots the caller or engine supplies at run time rather than the definition
_RUNTIME_ROOTS = frozenset({"goal", "user_id", "run_id", "model"})

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class ContractFinding:
    """One problem found by ``validate_contracts``."""

    severity: str  # "error" or "warning"
    task_id: str  # the task whose properties hold the reference
    ref: str  # the reference text, without braces
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: task '{self.task_id}' {{{{{self.ref}}}}}: {self.message}"


def _strings(value: Any) -> list[str]:
    """All string values nested in a properties structure."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _produced_properties(definition: ProcessDefinition) -> set[str]:
    """Process properties tasks write, named by their ``output_key`` / ``result_key`` / ... ."""
    return {
        value
        for task_def in definition.tasks.values()
        for key, value in task_def.properties.items()
        if key.endswith("_key") and isinstance(value, str)
    }


def _availability(definition: ProcessDefinition) -> tuple[dict[str, set], dict[str, set]]:
    """Per task, the tasks whose output must / may exist when it starts.

    A task reached through any one incoming routing needs the *intersection* of what its
    predecessors guarantee; a synchronized join waits for all of them, so takes the union.
    Solved to a fixpoint so loops terminate.
    """
    tasks = set(definition.tasks)
    incoming: dict[str, list[str]] = {t: [] for t in tasks}
    for routing in definition.routings:
        dest = routing.dest_task_id
        if dest in incoming and routing.source_task_id in tasks:
            incoming[dest].append(routing.source_task_id)

    must = {t: set(tasks) for t in tasks}  # start at top, shrink
    may: dict[str, set] = {t: set() for t in tasks}  # start at bottom, grow
    first = definition.first_task_id
    changed = True
    while changed:
        changed = False
        for t in tasks:
            preds = incoming[t]
            outs = [must[p] | {p} for p in preds]
            if t == first or not outs:
                new_must: set = set()
            elif definition.tasks[t].synchronized:
                new_must = set.union(*outs)
            else:
                new_must = set.intersection(*outs)
            new_may = set().union(*[may[p] | {p} for p in preds]) if preds else set()
            if new_must != must[t] or new_may != may[t]:
                must[t], may[t] = new_must, new_may
                changed = True
    return must, may


def validate_contracts(definition: ProcessDefinition) -> list[ContractFinding]:
    """Check the template references in a definition's task properties.

    Findings:
      * error: ``{{x.output}}`` where ``x`` is not a task, or is a task no path to the
        referencing task runs;
      * warning: ``{{x.output}}`` where ``x`` runs on only some paths to the referencing task;
      * warning: a root that is no task, declared process property or runtime key.

    Args:
        definition: The definition to check.

    Returns:
        Findings, empty when the contracts hold.
    """
    must, may = _availability(definition)
    declared = set(definition.properties) | _produced_properties(definition)
    findings: list[ContractFinding] = []
    seen: set[tuple[str, str]] = set()

    for task_id, task_def in definition.tasks.items():
        for text in _strings(task_def.properties):
            for ref in TEMPLATE_REF.findall(text):
                if (task_id, ref) in seen:
                    continue
                seen.add((task_id, ref))
                root, *rest = ref.split(".")
                if rest == ["output"] and (root in definition.tasks or root not in declared):
                    if root not in definition.tasks:
                        findings.append(
                            ContractFinding(ERROR, task_id, ref, f"unknown task '{root}'")
                        )
                    elif root not in may[task_id]:
                        findings.append(
                            ContractFinding(
                                ERROR, task_id, ref, f"no path runs '{root}' before '{task_id}'"
                            )
                        )
                    elif root not in must[task_id]:
                        findings.append(
                            ContractFinding(
                                WARNING,
                                task_id,
                                ref,
                                f"'{root}' runs on only some paths to '{task_id}'",
                            )
                        )
                elif (
                    root not in definition.tasks
                    and root not in declared
                    and root not in _RUNTIME_ROOTS
                    and not root.startswith("__")
                ):
                    findings.append(
                        ContractFinding(
                            WARNING, task_id, ref, f"'{root}' is not declared by the definition"
                        )
                    )
    return findings


_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}


def validate_output_schema(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """Validate *value* against a JSON Schema subset: type, enum, required, properties, items.

    Returns:
        One message per violation, each naming the offending path; empty when valid.
    """
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        names = expected if isinstance(expected, list) else [expected]
        allowed = tuple(t for n in names for t in _TYPES.get(n, ()))
        is_bool = isinstance(value, bool)
        number_ok = any(n in ("number", "integer") for n in names)
        if not isinstance(value, allowed) or (is_bool and number_ok and "boolean" not in names):
            return [f"{path}: expected {'/'.join(names)}, got {type(value).__name__}"]
        if "integer" in names and "number" not in names and isinstance(value, float):
            return [f"{path}: expected integer, got float"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key '{key}'")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors.extend(validate_output_schema(sub, value[key], f"{path}.{key}"))
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors.extend(validate_output_schema(schema["items"], item, f"{path}[{i}]"))
    return errors

"""JSON select / filter / sort / pick task action."""

import logging
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.data._common import input_value
from zebra_tasks.llm.structured import parse_llm_json

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\.?([^.\[\]]+)|\[(-?\d+|\*)\]")
WILDCARD = "*"


def parse_path(path: str) -> list[str | int]:
    """Split ``a.b[0].c`` / ``items[*].name`` into keys, indexes and ``*``.

    Raises:
        ValueError: The path is empty or malformed.
    """
    tokens: list[str | int] = []
    pos = 0
    path = path.strip()
    while pos < len(path):
        match = _TOKEN_RE.match(path, pos)
        if not match or (match.group(0).startswith(".") and pos == 0):
            raise ValueError(f"invalid path {path!r} at position {pos}")
        key, index = match.groups()
        if key is not None:
            tokens.append(key)
        else:
            tokens.append(WILDCARD if index == WILDCARD else int(index))
        pos = match.end()
    if not tokens:
        raise ValueError("path is empty")
    return tokens


def get_path(value: Any, tokens: list[str | int]) -> Any:
    """Follow ``tokens`` into ``value``; a missing key or index gives ``None``.

    ``*`` maps the rest of the path over a list (a single non-list value is
    treated as a one-item list, softening XML's one-vs-many ambiguity).
    """
    for i, token in enumerate(tokens):
        if token == WILDCARD:
            items = value if isinstance(value, list) else [] if value is None else [value]
            return [get_path(item, tokens[i + 1 :]) for item in items]
        if isinstance(token, int):
            if not isinstance(value, list) or not -len(value) <= token < len(value):
                return None
            value = value[token]
        elif isinstance(value, dict):
            value = value.get(token)
        else:
            return None
    return value


def _matches(actual: Any, expected: Any) -> bool:
    """Equality, comparing as text when the types differ (CSV values are strings)."""
    if actual == expected:
        return True
    return actual is not None and expected is not None and str(actual) == str(expected)


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _sort_key_fn(values: list[Any]):
    """Pick a sort key: numeric when every non-null value is a number, else native/text."""
    present = [v for v in values if v is not None]
    if all(_is_number(v) for v in present):
        return lambda v: (v is None, 0.0 if v is None else float(v))
    try:
        sorted(present)
        return lambda v: (v is None, v if v is not None else 0)
    except TypeError:
        return lambda v: (v is None, "" if v is None else str(v))


def transform(value: Any, props: dict[str, Any]) -> Any:
    """Apply ``path`` → ``where`` → ``sort_by`` → ``limit`` → ``pick`` to ``value``.

    Raises:
        ValueError: A step is misconfigured or applied to the wrong kind of value.
    """
    if props.get("path"):
        value = get_path(value, parse_path(str(props["path"])))

    where = props.get("where")
    if where:
        if not isinstance(where, dict):
            raise ValueError("'where' must be a mapping of path: value")
        if not isinstance(value, list):
            raise ValueError("'where' needs a list")
        conditions = [(parse_path(str(p)), expected) for p, expected in where.items()]
        value = [
            item
            for item in value
            if all(_matches(get_path(item, tokens), exp) for tokens, exp in conditions)
        ]

    if props.get("sort_by"):
        if not isinstance(value, list):
            raise ValueError("'sort_by' needs a list")
        tokens = parse_path(str(props["sort_by"]))
        keys = [get_path(item, tokens) for item in value]
        key_fn = _sort_key_fn(keys)
        order = sorted(range(len(value)), key=lambda i: key_fn(keys[i]))
        if props.get("descending"):
            # Reverse the present values but keep nulls last.
            present = [i for i in order if keys[i] is not None][::-1]
            order = present + [i for i in order if keys[i] is None]
        value = [value[i] for i in order]

    if props.get("limit") is not None:
        if not isinstance(value, list):
            raise ValueError("'limit' needs a list")
        try:
            limit = int(props["limit"])
        except (TypeError, ValueError) as e:
            raise ValueError("'limit' must be an integer") from e
        value = value[: max(limit, 0)]

    pick = props.get("pick")
    if pick:
        fields = [pick] if isinstance(pick, str) else list(pick)
        paths = [(str(f), parse_path(str(f))) for f in fields]
        if isinstance(value, dict):
            value = {name: get_path(value, tokens) for name, tokens in paths}
        elif isinstance(value, list):
            value = [{name: get_path(item, tokens) for name, tokens in paths} for item in value]
        else:
            raise ValueError("'pick' needs a dict or a list")
    return value


class TransformJsonAction(TaskAction):
    """Select, filter, sort, limit and pick fields from JSON data.

    ``data`` may be a value, a pure ``{{template}}`` (structure kept) or a JSON
    string — code fences and surrounding prose are tolerated, so an
    ``llm_call`` reply works directly. Steps run in a fixed order:
    ``path`` → ``where`` → ``sort_by`` (+ ``descending``) → ``limit`` → ``pick``.
    Paths look like ``a.b[0].c`` or ``items[*].name``; a missing key gives null.

    Example workflow usage:
        ```yaml
        tasks:
          top_open:
            name: "Top open issues"
            action: transform_json
            properties:
              data: "{{issues_json}}"
              path: "items"
              where: {state: open}
              sort_by: votes
              descending: true
              limit: 5
              pick: [title, url]
              output_key: top_issues
        ```

    Output:
        - result: the transformed value
        - count: number of items when the result is a list
    """

    description = (
        "Select (path), filter (where), sort, limit and pick fields from JSON data or an "
        "LLM's JSON reply, deterministically and without an LLM call."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="data",
            type="any",
            description="Value, {{template}}, or JSON text (fences/prose tolerated)",
            required=True,
        ),
        ParameterDef(
            name="path",
            type="string",
            description="Select a sub-value: a.b[0].c, items[*].name",
            required=False,
        ),
        ParameterDef(
            name="where",
            type="dict",
            description="Keep list items whose path equals the value (all must match)",
            required=False,
        ),
        ParameterDef(
            name="sort_by",
            type="string",
            description="Sort list items by this path (numeric when all values are numbers)",
            required=False,
        ),
        ParameterDef(
            name="descending",
            type="bool",
            description="Sort descending (nulls stay last)",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="limit", type="int", description="Keep the first N list items", required=False
        ),
        ParameterDef(
            name="pick",
            type="list",
            description="Paths to keep from each item (or from a dict)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="json_result",
        ),
    ]

    outputs = [
        ParameterDef(name="result", type="any", description="Transformed value", required=True),
        ParameterDef(name="count", type="int", description="Items, for a list", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Transform the data and store the result."""
        try:
            value = input_value(task, context)
            if isinstance(value, str):
                value = parse_llm_json(value)
            value = transform(value, task.properties)
        except ValueError as e:
            return TaskResult.fail(f"transform_json: {e}")

        result: dict[str, Any] = {"result": value}
        if isinstance(value, list):
            result["count"] = len(value)
        context.set_process_property(task.properties.get("output_key", "json_result"), result)
        logger.info("transform_json: %s item(s)", result.get("count", 1))
        return TaskResult.ok(output=result)

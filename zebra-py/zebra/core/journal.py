"""Process step journal helpers (#184).

The engine records a ``ProcessEvent`` at each process and task lifecycle step,
carrying the process-property diff made since the previous step. These helpers
compute that diff and replay it to rebuild properties at any step.
"""

import copy
import json
from typing import Any

from zebra.core.models import ProcessEvent

#: Property values whose JSON form exceeds this many characters are journalled
#: as a truncated preview, so a large blob is not copied into every step.
MAX_JOURNAL_VALUE_CHARS = 16_000

#: Characters of a truncated value kept as its preview.
TRUNCATED_PREVIEW_CHARS = 2_000

#: Marker key on a journalled value that was too large to keep whole.
TRUNCATED_KEY = "__journal_truncated__"


def snapshot(properties: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *properties* to diff against after a step."""
    return copy.deepcopy(properties)


def _cap(value: Any) -> Any:
    """Return *value*, or a truncated preview if its JSON form is too large."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_JOURNAL_VALUE_CHARS:
        return value
    return {
        TRUNCATED_KEY: True,
        "size": len(text),
        "preview": text[:TRUNCATED_PREVIEW_CHARS],
    }


def property_diff(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return the properties set or changed, and the keys removed, from *before* to *after*.

    Changed values are capped to ``MAX_JOURNAL_VALUE_CHARS``.
    """
    changed = {k: _cap(v) for k, v in after.items() if k not in before or before[k] != v}
    removed = sorted(k for k in before if k not in after)
    return changed, removed


def replay(events: list[ProcessEvent]) -> list[dict[str, Any]]:
    """Return the process properties after each of *events*, applied in order.

    *events* must belong to one process. Element ``i`` is the full property
    dict as it stood once event ``i`` was applied.
    """
    current: dict[str, Any] = {}
    states: list[dict[str, Any]] = []
    for event in events:
        current = {k: v for k, v in current.items() if k not in event.removed}
        current.update(event.changed)
        states.append(dict(current))
    return states

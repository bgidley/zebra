"""LoadValuesProfileAction — read the current values profile for a user.

Used by the values-profile wizard workflow as its first step. In capture mode,
the user has no profile yet and the action returns ``found=False`` (form
defaults stay empty). In edit mode, the action loads the current
``ValuesProfileVersion`` and writes its fields into process properties under
``existing_profile``, so subsequent human-task forms can pre-populate via
``default: "{{existing_profile.<field>_text}}"`` template references.
"""

from __future__ import annotations

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class LoadValuesProfileAction(TaskAction):
    """Load the current values-profile version (if any) for the wizard.

    Properties:
        user_id: The authenticated user's id (required)
        output_key: Where to store the loaded profile dict (default: ``existing_profile``)

    Output:
        - found: bool — whether a current version was found
        - mode: "edit" if found, "capture" otherwise
    """

    description = "Load a user's current values-profile version into process properties."

    inputs = [
        ParameterDef(
            name="user_id",
            type="number",
            description="Authenticated user's id",
            required=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the loaded profile",
            required=False,
            default="existing_profile",
        ),
    ]

    outputs = [
        ParameterDef(
            name="found",
            type="bool",
            description="Whether a current version was found",
            required=True,
        ),
        ParameterDef(
            name="mode",
            type="string",
            description="'edit' if found, 'capture' otherwise",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        user_id = task.properties.get("user_id")
        if isinstance(user_id, str) and "{{" in user_id:
            user_id = context.resolve_template(user_id)
        try:
            user_id = int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            return TaskResult.fail(f"Invalid user_id: {user_id!r}")
        if user_id is None:
            return TaskResult.fail("user_id is required")

        output_key = task.properties.get("output_key", "existing_profile")

        profile_store = context.extras.get("__profile_store__")
        if profile_store is None:
            logger.warning("No profile store available — running in capture mode")
            context.set_process_property(output_key, _empty_profile_dict())
            return TaskResult.ok(output={"found": False, "mode": "capture"})

        version = await profile_store.get_current(user_id=user_id)
        if version is None:
            saved = _empty_profile_dict()
            saved["mode"] = "capture"
            context.set_process_property(output_key, saved)
            return TaskResult.ok(output={"found": False, "mode": "capture"})

        saved = version.to_dict()
        saved["mode"] = "edit"
        context.set_process_property(output_key, saved)
        return TaskResult.ok(output={"found": True, "mode": "edit"})


def _empty_profile_dict() -> dict:
    """Empty profile dict for capture mode — keeps template lookups safe."""
    return {
        "id": "",
        "version_number": 0,
        "core_values_text": "",
        "core_values_tags": [],
        "ethical_positions_text": "",
        "ethical_positions_tags": [],
        "priorities_text": "",
        "priorities_tags": [],
        "deal_breakers_text": "",
        "deal_breakers_tags": [],
    }

"""SaveValuesProfileAction — persist a new ValuesProfileVersion plus tag confirmations.

Final step of the values-profile wizard. Pulls the user's confirmed text fields
and tag selections from process properties and writes them via ``ProfileStore``:

1. ``save_version(user_id, version)`` — creates the immutable version row,
   bumps ``ValuesProfile.current_version``.
2. ``record_confirmed_tags(...)`` — upserts each confirmed tag, incrementing
   ``usage_count`` on existing rows or creating new ``status="candidate"`` rows.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction
from zebra_agent.profile import ValuesProfileVersion

logger = logging.getLogger(__name__)


_FIELDS = ("core_values", "ethical_positions", "priorities", "deal_breakers")


class SaveValuesProfileAction(TaskAction):
    """Persist the wizard output as a new ValuesProfileVersion."""

    description = "Save the values profile, creating a new immutable version and tag rows."

    inputs = [
        ParameterDef(
            name="user_id",
            type="number",
            description="Authenticated user's id",
            required=True,
        ),
        ParameterDef(
            name="confirmed",
            type="dict",
            description=(
                "Per-field confirmed payload: "
                "{<field>: {text: str, tags: [{slug, label}, ...]}, ...}"
            ),
            required=True,
        ),
        ParameterDef(
            name="extraction_model",
            type="string",
            description="Model id from the extract step (stored on the version)",
            required=False,
            default="",
        ),
        ParameterDef(
            name="created_via",
            type="string",
            description="'wizard' | 'edit' | 'restore'",
            required=False,
            default="wizard",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the saved-version summary",
            required=False,
            default="saved_profile",
        ),
    ]

    outputs = [
        ParameterDef(
            name="version_id",
            type="string",
            description="The id of the newly persisted ValuesProfileVersion",
            required=True,
        ),
        ParameterDef(
            name="version_number",
            type="number",
            description="The monotonic version number of the new version",
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

        confirmed = task.properties.get("confirmed")
        if isinstance(confirmed, str) and "{{" in confirmed:
            confirmed = context.resolve_template(confirmed)
        if not isinstance(confirmed, dict):
            return TaskResult.fail("'confirmed' must be a dict of per-field payloads")

        extraction_model = task.properties.get("extraction_model") or ""
        created_via = task.properties.get("created_via", "wizard") or "wizard"
        output_key = task.properties.get("output_key", "saved_profile")

        profile_store = context.extras.get("__profile_store__")
        if profile_store is None:
            return TaskResult.fail("No profile store available — cannot save values profile")

        # Build the ValuesProfileVersion draft from confirmed payload.
        kwargs: dict = {
            "created_via": created_via,
            "tags_extracted_at": datetime.now(UTC) if extraction_model else None,
            "tags_extraction_model": extraction_model or None,
        }
        for field in _FIELDS:
            field_payload = confirmed.get(field, {}) or {}
            text = field_payload.get("text", "") or ""
            tags = field_payload.get("tags", []) or []
            tag_slugs = [_tag_slug(t) for t in tags if _tag_slug(t)]
            kwargs[f"{field}_text"] = text
            kwargs[f"{field}_tags"] = tag_slugs

        draft = ValuesProfileVersion(**kwargs)

        try:
            persisted = await profile_store.save_version(user_id=user_id, version=draft)
        except Exception as exc:
            logger.exception("Failed to save values profile version")
            return TaskResult.fail(f"Failed to save values profile: {exc}")

        # Record tag usage / candidate creation. Failure here should not roll
        # back the version save — tags are auxiliary.
        try:
            field_to_tags: dict[str, list[dict[str, str]]] = {}
            for field in _FIELDS:
                tags = (confirmed.get(field, {}) or {}).get("tags") or []
                normalised = [_normalise_tag(t) for t in tags]
                normalised = [t for t in normalised if t.get("slug")]
                if normalised:
                    field_to_tags[field] = normalised
            if field_to_tags:
                await profile_store.record_confirmed_tags(field_to_tags)
        except Exception as exc:
            logger.warning("Failed to record confirmed tags: %s", exc)

        result = {
            "version_id": persisted.id,
            "version_number": persisted.version_number,
        }
        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)


def _tag_slug(tag) -> str:  # type: ignore[no-untyped-def]
    if isinstance(tag, str):
        return tag
    if isinstance(tag, dict):
        return str(tag.get("slug") or "")
    return ""


def _normalise_tag(tag) -> dict[str, str]:  # type: ignore[no-untyped-def]
    slug = _tag_slug(tag)
    if isinstance(tag, dict):
        label = str(tag.get("label") or slug)
        description = str(tag.get("description") or "")
        return {"slug": slug, "label": label, "description": description}
    return {"slug": slug, "label": slug}

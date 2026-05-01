"""ExtractValuesTagsAction — LLM-driven tag extraction from free-form text.

Reads the four free-form text fields the user filled in earlier wizard steps,
plus the approved-tag set per field from ``ProfileStore``, and asks the LLM to
return a structured ``{<field>: {approved_tags, candidate_tags}}`` mapping.
Approved tags are those the LLM matched from the existing taxonomy; candidate
tags are new suggestions not yet in the taxonomy.

If anything goes wrong (LLM error, parse error, missing store), the action
still returns success with empty tag sets — the wizard's review step is the
single point at which tags are persisted, so the user can always fill in tags
manually after extraction failure.
"""

from __future__ import annotations

import json
import logging
import re

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm import get_provider

logger = logging.getLogger(__name__)


_FIELDS = ("core_values", "ethical_positions", "priorities", "deal_breakers")


SYSTEM_PROMPT = """\
You are a values-profile tag extractor. The user has filled out four free-form
text fields describing their values. For each field, you are given a list of
APPROVED TAGS already in the taxonomy. Your job is to:

1. Pick approved tags from the supplied list that match what the user wrote.
2. Optionally suggest CANDIDATE tags — short concept slugs (kebab-case) that
   capture an idea the user expressed but that is not in the approved list.

Output strictly valid JSON of the shape:

{
  "<field>": {
    "approved_tags": ["slug-1", "slug-2"],
    "candidate_tags": [{"slug": "new-slug", "label": "New Label"}]
  }
}

— with a top-level entry for each of: core_values, ethical_positions,
priorities, deal_breakers.

Constraints:
- Only include slugs in `approved_tags` that exactly match an approved-tag slug.
- Cap candidate tags at 5 per field. Prefer tags the user clearly emphasised.
- Use kebab-case for slugs (e.g. "no-deception", "family-time").
"""


class ExtractValuesTagsAction(TaskAction):
    """LLM-extract approved + candidate tags from the user's text fields."""

    description = "Extract structured tags from the four free-form values fields via an LLM."

    inputs = [
        ParameterDef(
            name="core_values_text",
            type="string",
            description="Free-form text for core values",
            required=False,
            default="",
        ),
        ParameterDef(
            name="ethical_positions_text",
            type="string",
            description="Free-form text for ethical positions",
            required=False,
            default="",
        ),
        ParameterDef(
            name="priorities_text",
            type="string",
            description="Free-form text for priorities",
            required=False,
            default="",
        ),
        ParameterDef(
            name="deal_breakers_text",
            type="string",
            description="Free-form text for deal-breakers",
            required=False,
            default="",
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider name",
            required=False,
            default="anthropic",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="LLM model alias or full id",
            required=False,
            default="haiku",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the extracted tags",
            required=False,
            default="extracted_tags",
        ),
    ]

    outputs = [
        ParameterDef(
            name="extracted_tags",
            type="dict",
            description="Per-field {approved_tags, candidate_tags} mapping",
            required=True,
        ),
        ParameterDef(
            name="model",
            type="string",
            description="The LLM model id used for extraction (empty on failure)",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        texts = {field: _resolve(task, context, f"{field}_text") for field in _FIELDS}
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model", "haiku")
        output_key = task.properties.get("output_key", "extracted_tags")

        empty_result = _empty_extraction()
        profile_store = context.extras.get("__profile_store__")
        if profile_store is None:
            logger.warning("No profile store — returning empty extracted tags")
            return self._finish(context, output_key, empty_result, model_used="")

        try:
            approved_by_field: dict[str, list[dict]] = {}
            for field in _FIELDS:
                approved_by_field[field] = await profile_store.get_approved_tags(field)
        except Exception as exc:
            logger.warning("Failed to load approved tags: %s — returning empty", exc)
            return self._finish(context, output_key, empty_result, model_used="")

        prompt = _build_prompt(texts, approved_by_field)

        try:
            provider = get_provider(provider_name, model=model)
        except Exception as exc:
            logger.warning("Failed to construct LLM provider: %s — returning empty", exc)
            return self._finish(context, output_key, empty_result, model_used="")

        try:
            from zebra_tasks.llm.base import Message

            response = await provider.complete(
                messages=[
                    Message(role="system", content=SYSTEM_PROMPT),
                    Message(role="user", content=prompt),
                ],
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as exc:
            logger.warning("LLM call failed during tag extraction: %s — returning empty", exc)
            return self._finish(context, output_key, empty_result, model_used="")

        parsed = _parse_response(response.content, approved_by_field)
        if parsed is None:
            logger.warning("Failed to parse LLM response — returning empty")
            return self._finish(context, output_key, empty_result, model_used=response.model)

        return self._finish(context, output_key, parsed, model_used=response.model)

    @staticmethod
    def _finish(
        context: ExecutionContext,
        output_key: str,
        extracted: dict,
        model_used: str,
    ) -> TaskResult:
        result = {"extracted_tags": extracted, "model": model_used}
        context.set_process_property(output_key, extracted)
        return TaskResult.ok(output=result)


def _resolve(task: TaskInstance, context: ExecutionContext, key: str) -> str:
    value = task.properties.get(key, "")
    if isinstance(value, str) and "{{" in value:
        value = context.resolve_template(value)
    return value or ""


def _empty_extraction() -> dict:
    return {field: {"approved_tags": [], "candidate_tags": []} for field in _FIELDS}


def _build_prompt(texts: dict[str, str], approved_by_field: dict[str, list[dict]]) -> str:
    lines = []
    for field in _FIELDS:
        lines.append(f"## {field}")
        lines.append("")
        lines.append("Approved tags:")
        if approved_by_field[field]:
            for tag in approved_by_field[field]:
                desc = tag.get("description") or ""
                label = tag.get("label", tag["slug"])
                lines.append(f"  - {tag['slug']} — {label}: {desc}".rstrip())
        else:
            lines.append("  (none yet)")
        lines.append("")
        lines.append("User text:")
        lines.append(texts.get(field, "") or "(empty)")
        lines.append("")
    lines.append("Return strictly valid JSON as specified in the system prompt.")
    return "\n".join(lines)


def _parse_response(content: str, approved_by_field: dict[str, list[dict]]) -> dict | None:
    """Extract a JSON object from the LLM response and validate the shape."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    approved_slugs = {field: {t["slug"] for t in approved_by_field[field]} for field in _FIELDS}

    result: dict[str, dict] = {}
    for field in _FIELDS:
        per_field = data.get(field, {}) or {}
        approved = [s for s in (per_field.get("approved_tags") or []) if s in approved_slugs[field]]
        raw_candidates = per_field.get("candidate_tags") or []
        candidates: list[dict[str, str]] = []
        for cand in raw_candidates:
            if isinstance(cand, str):
                candidates.append({"slug": cand, "label": cand.replace("-", " ").title()})
            elif isinstance(cand, dict) and "slug" in cand:
                candidates.append(
                    {
                        "slug": str(cand["slug"]),
                        "label": str(cand.get("label") or cand["slug"]),
                    }
                )
        # Drop candidates whose slug is already approved.
        candidates = [c for c in candidates if c["slug"] not in approved_slugs[field]][:5]
        result[field] = {"approved_tags": approved, "candidate_tags": candidates}
    return result

"""ExtractKnowledgeAction — LLM extraction of personal knowledge candidates (F152).

Reads what the user said during a goal run (goal text, answers to human tasks,
continuation comment) plus the run's result, and asks an LLM for durable facts
about the user. Returns validated candidates
``{category, key, value, time_sensitive, confidence}`` without writing anything:
storing is the caller's job (``store_learned_knowledge`` in the agent main loop).

Kept independent of the agent main loop so other workflows (e.g. a dream-cycle
knowledge review) can reuse it with their own text inputs.
"""

import json
import logging
import os
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 5
DEFAULT_MIN_CONFIDENCE = 0.5
MAX_KEY_LEN = 64
MAX_VALUE_LEN = 500
_MAX_TEXT_LEN = 3000
_MAX_EXISTING = 50

# Values that must never be stored, whatever the user opted in to.
_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(password|passcode|passwd|pin code|api[_ -]?key|secret|token)\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # payment card / account-like digit runs
    re.compile(r"(?i)\b(?:sk|pk|ghp|glpat|xox[bp])[-_][A-Za-z0-9_-]{8,}"),  # API tokens
]
_KEY_PREFIXES = ("user_", "users_", "my_", "the_")

SYSTEM_PROMPT = """\
You extract durable personal knowledge about the USER from an AI agent's goal run.

Only extract facts the user stated or clearly confirmed about themselves: where they
work or live, people in their life, preferences, routines, skills, notable history.
Do NOT extract:
- facts about the world, or anything the agent produced, suggested or assumed;
- one-off task details ("wants a poem about cats" is not a preference);
- passwords, API keys, account or card numbers, government ID numbers.

Mark "sensitive": true for special-category data: health, sexual orientation or sex
life, religious or philosophical beliefs, political opinions, racial or ethnic
origin, trade-union membership, genetic or biometric data, criminal record.

Categories (use exactly one): {categories}.
Keys are short snake_case nouns naming the fact (e.g. "employer", "home_city",
"partner_name", "preferred_language"). If an existing key below names the same
fact, reuse that key exactly instead of inventing a new one.
"time_sensitive" is true when the fact is likely to change (job, address, routine).
"confidence" (0-1) is how sure you are the user really stated this about themselves.

Most runs contain nothing personal: then return an empty list. Never invent facts.

Respond with JSON only:
{{"candidates": [{{"category": "...", "key": "...", "value": "...",
  "time_sensitive": true, "confidence": 0.8, "sensitive": false}}]}}"""

USER_PROMPT = """\
Existing knowledge keys (category/key: value):
{existing}

Goal:
{goal}

User's answers to questions during the run:
{user_inputs}

User's continuation comment:
{continuation_comment}

Run result (context only — not a source of facts by itself):
{result}"""


def normalize_knowledge_key(key: Any) -> str:
    """Normalise a knowledge key to ``snake_case`` so one fact keeps one key.

    Lower-cases, turns any non-alphanumeric run into ``_``, drops filler prefixes
    such as ``user_`` / ``my_``, and truncates to ``MAX_KEY_LEN``.
    """
    text = re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")
    for prefix in _KEY_PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix) :]
            break
    return text[:MAX_KEY_LEN].strip("_")


def looks_secret(value: str) -> bool:
    """True if the value looks like a credential or account/card number."""
    text = value.replace("_", " ")
    return any(p.search(value) or p.search(text) for p in _SECRET_PATTERNS)


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _as_text(value: Any, limit: int = _MAX_TEXT_LEN) -> str:
    """Render any JSON-ish value as prompt text, truncated."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    return text[:limit]


def resolve_raw(context: ExecutionContext, value: Any) -> Any:
    """Resolve a property that may be a template, keeping structure.

    ``"{{a.b}}"`` on its own returns the raw value at ``a.b`` (dicts and lists stay
    intact); any other template is resolved to a string.
    """
    if not isinstance(value, str) or "{{" not in value:
        return value
    match = re.fullmatch(r"\s*\{\{(\w+(?:\.\w+)*)\}\}\s*", value)
    if match:
        parts = match.group(1).split(".")
        obj: Any = context.process.properties.get(parts[0])
        for part in parts[1:]:
            obj = obj.get(part) if isinstance(obj, dict) else None
        if obj is not None:
            return obj
    return context.resolve_template(value)


def _parse_json(content: str) -> Any:
    content = content or ""
    if "```" in content:
        start = content.index("```") + 3
        if content[start:].startswith("json"):
            start += 4
        end = content.find("```", start)
        content = content[start : end if end != -1 else None]
    return json.loads(content.strip())


def validate_candidates(
    raw: Any,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    allow_sensitive: bool = False,
    existing_keys: dict[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate and normalise LLM candidates, applying the privacy guardrails.

    Returns:
        ``(candidates, dropped)``; each dropped item carries a ``reason``.
    """
    from zebra_agent.knowledge import KNOWLEDGE_CATEGORIES

    items = raw.get("candidates", []) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return [], []

    existing_keys = existing_keys or {}
    candidates: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip().lower()
        key = normalize_knowledge_key(item.get("key"))
        value = str(item.get("value") or "").strip()[:MAX_VALUE_LEN]
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

        reason = None
        if category not in KNOWLEDGE_CATEGORIES:
            reason = "invalid_category"
        elif not key or not value:
            reason = "empty"
        elif looks_secret(value) or looks_secret(key):
            reason = "secret"
        elif _as_bool(item.get("sensitive", False)) and not allow_sensitive:
            reason = "sensitive"
        elif confidence < min_confidence:
            reason = "low_confidence"
        elif (category, key) in seen:
            reason = "duplicate"
        elif len(candidates) >= max_entries:
            reason = "cap"
        if reason:
            dropped.append({"category": category, "key": key, "reason": reason})
            continue

        seen.add((category, key))
        candidates.append(
            {
                "category": category,
                "key": key,
                "value": value,
                "time_sensitive": _as_bool(item.get("time_sensitive", False)),
                "confidence": round(confidence, 2),
                "existing_key": key in existing_keys.get(category, set()),
            }
        )
    return candidates, dropped


class ExtractKnowledgeAction(TaskAction):
    """Extract candidate personal knowledge from a goal run with an LLM.

    Skips (no LLM call) when there is no user, or no user-authored text at all.
    Never writes to the knowledge store and never fails the workflow: provider
    errors and unparseable responses yield an empty candidate list.

    Guardrails: categories must be in ``KNOWLEDGE_CATEGORIES``; keys are
    normalised (``normalize_knowledge_key``) and existing keys are offered to the
    LLM for reuse; credential-like values are always dropped; special-category
    (``sensitive``) facts are dropped unless ``allow_sensitive`` is true (or env
    ``ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE`` is set); at most ``max_entries`` are kept.

    Routes: ``has_candidates`` / ``no_candidates``.
    """

    description = "LLM-extract durable personal knowledge candidates about the user from a run."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="goal", type="string", description="Goal text", required=False),
        ParameterDef(
            name="user_inputs",
            type="any",
            description="User answers to human tasks (dict, list or text)",
            required=False,
        ),
        ParameterDef(
            name="continuation_comment",
            type="string",
            description="User's continuation comment, if any",
            required=False,
        ),
        ParameterDef(
            name="result", type="any", description="Run result (context only)", required=False
        ),
        ParameterDef(
            name="user_id",
            type="int",
            description="User id; defaults to the __user_id__ process property",
            required=False,
        ),
        ParameterDef(
            name="max_entries",
            type="int",
            description="Maximum candidates returned",
            required=False,
            default=DEFAULT_MAX_ENTRIES,
        ),
        ParameterDef(
            name="min_confidence",
            type="float",
            description="Drop candidates the LLM is less sure of than this",
            required=False,
            default=DEFAULT_MIN_CONFIDENCE,
        ),
        ParameterDef(
            name="allow_sensitive",
            type="bool",
            description="Keep special-category facts (user opt-in)",
            required=False,
            default=False,
        ),
        ParameterDef(name="provider", type="string", description="LLM provider", required=False),
        ParameterDef(
            name="model", type="string", description="LLM model (default haiku)", required=False
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="knowledge_candidates",
        ),
    ]

    outputs = [
        ParameterDef(
            name="candidates",
            type="list",
            description="Validated {category, key, value, time_sensitive, confidence} dicts",
            required=True,
        ),
        ParameterDef(name="count", type="int", description="Number of candidates", required=True),
        ParameterDef(name="dropped", type="list", description="Rejected candidates with reasons"),
        ParameterDef(name="skipped", type="string", description="Why extraction was skipped"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        props = task.properties
        output_key = props.get("output_key", "knowledge_candidates")

        def _finish(candidates: list, dropped: list | None = None, skipped: str = "") -> TaskResult:
            result = {
                "candidates": candidates,
                "count": len(candidates),
                "dropped": dropped or [],
                "skipped": skipped,
            }
            context.set_process_property(output_key, result)
            route = "has_candidates" if candidates else "no_candidates"
            return TaskResult(success=True, output=result, next_route=route)

        user_id = resolve_raw(context, props.get("user_id")) or context.get_process_property(
            "__user_id__"
        )
        if user_id in (None, ""):
            logger.info("ExtractKnowledgeAction: no user_id — skipping")
            return _finish([], skipped="no_user")

        goal = _as_text(resolve_raw(context, props.get("goal", "")))
        user_inputs = _as_text(resolve_raw(context, props.get("user_inputs", "")))
        comment = _as_text(resolve_raw(context, props.get("continuation_comment", "")))
        result_text = _as_text(resolve_raw(context, props.get("result", "")), 2000)
        if not (goal or user_inputs or comment):
            return _finish([], skipped="no_user_text")

        max_entries = int(props.get("max_entries", DEFAULT_MAX_ENTRIES))
        min_confidence = float(props.get("min_confidence", DEFAULT_MIN_CONFIDENCE))
        allow_sensitive = _as_bool(
            resolve_raw(context, props.get("allow_sensitive", False))
        ) or _as_bool(os.environ.get("ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE", ""))

        existing_keys, existing_text = await self._existing(context, user_id)

        provider_name = (
            props.get("provider")
            or context.process.properties.get("__llm_provider_name__")
            or "anthropic"
        )
        model = props.get("model") or "haiku"
        try:
            from zebra_agent.knowledge import KNOWLEDGE_CATEGORIES

            provider = get_provider(provider_name, model)
            response = await provider.complete(
                messages=[
                    Message.system(
                        SYSTEM_PROMPT.format(categories=", ".join(KNOWLEDGE_CATEGORIES))
                    ),
                    Message.user(
                        USER_PROMPT.format(
                            existing=existing_text or "(none)",
                            goal=goal or "(none)",
                            user_inputs=user_inputs or "(none)",
                            continuation_comment=comment or "(none)",
                            result=result_text or "(none)",
                        )
                    ),
                ],
                temperature=0.0,
                max_tokens=800,
            )
            parsed = _parse_json(response.content)
        except Exception as e:  # provider, network or JSON errors — never block the run
            logger.warning("ExtractKnowledgeAction: extraction failed — %s", e)
            return _finish([], skipped=f"error: {e}"[:200])

        candidates, dropped = validate_candidates(
            parsed,
            max_entries=max_entries,
            min_confidence=min_confidence,
            allow_sensitive=allow_sensitive,
            existing_keys=existing_keys,
        )
        logger.info(
            "ExtractKnowledgeAction: %d candidate(s), %d dropped", len(candidates), len(dropped)
        )
        return _finish(candidates, dropped)

    async def _existing(
        self, context: ExecutionContext, user_id: Any
    ) -> tuple[dict[str, set[str]], str]:
        """Existing keys per category, and a prompt listing, so the LLM reuses keys."""
        store = context.extras.get("__knowledge_store__")
        if store is None:
            return {}, ""
        try:
            entries = await store.get_entries(int(user_id))
        except Exception as e:
            logger.warning("ExtractKnowledgeAction: could not read existing knowledge: %s", e)
            return {}, ""
        keys: dict[str, set[str]] = {}
        for e in entries:
            keys.setdefault(e.category, set()).add(e.key)
        lines = [f"{e.category}/{e.key}: {e.value[:80]}" for e in entries[:_MAX_EXISTING]]
        return keys, "\n".join(lines)

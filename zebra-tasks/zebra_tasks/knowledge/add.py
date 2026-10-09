"""AddKnowledgeAction — store a knowledge entry with contradiction detection."""

import logging
from datetime import UTC, datetime
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


async def store_knowledge_entry(
    knowledge_store: Any,
    *,
    user_id: int,
    category: str,
    key: str,
    value: str,
    source: str = "agent",
    time_sensitive: bool = False,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Store one knowledge entry with contradiction detection (shared core of add_knowledge).

    Never overwrites an existing entry with a different value: that is reported
    as a contradiction for the caller to resolve.

    - No live entry for ``(user_id, category, key)``: create it. ``confidence``
      defaults to 1.0.
    - Same value: refresh ``last_verified``. A ``human`` write, or one without an
      explicit ``confidence``, confirms the entry (confidence 1.0); an ``agent``
      write with a ``confidence`` keeps the higher of the old and new confidence,
      so agent re-observations never reach 1.0 on their own.
    - Different value: write nothing.

    Returns:
        ``{status, entry_id, existing_value, existing_source}`` where ``status`` is
        ``created``, ``refreshed`` or ``contradiction``.
    """
    from zebra_agent.knowledge import KnowledgeEntry

    existing = await knowledge_store.find_contradicting_entry(user_id, category, key)

    if existing is None:
        entry = KnowledgeEntry.create(
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            source=source,
            confidence=1.0 if confidence is None else confidence,
            time_sensitive=time_sensitive,
        )
        await knowledge_store.add_entry(entry)
        logger.info("store_knowledge_entry: stored new entry %s (%s)", entry.id, source)
        return {
            "status": "created",
            "entry_id": entry.id,
            "existing_value": "",
            "existing_source": "",
        }

    if existing.value == value:
        now = datetime.now(UTC)
        existing.last_verified = now
        existing.updated_at = now
        if source == "human" or confidence is None:
            existing.confidence = 1.0
        else:
            existing.confidence = max(existing.confidence, confidence)
        await knowledge_store.update_entry(existing)
        logger.info("store_knowledge_entry: refreshed existing entry %s", existing.id)
        return {
            "status": "refreshed",
            "entry_id": existing.id,
            "existing_value": existing.value,
            "existing_source": existing.source,
        }

    logger.info(
        "store_knowledge_entry: contradiction for key %r (existing=%r proposed=%r)",
        key,
        existing.value,
        value,
    )
    return {
        "status": "contradiction",
        "entry_id": existing.id,
        "existing_value": existing.value,
        "existing_source": existing.source,
    }


class AddKnowledgeAction(TaskAction):
    """Store a knowledge entry, routing to 'contradiction' if a conflicting entry exists.

    Before writing, checks for an existing non-deleted entry with the same
    (user_id, category, key). If found with a different value, returns
    ``next_route="contradiction"`` without writing. If found with the same value,
    refreshes ``last_verified`` and returns ``next_route="stored"``. Otherwise
    creates a new entry and returns ``next_route="stored"``.

    Requires ``__knowledge_store__`` in ``context.extras`` and ``__user_id__``
    in process properties.  Degrades gracefully when either is absent.

    Properties:
        category: Knowledge category (must be in KNOWLEDGE_CATEGORIES)
        key: The knowledge key
        value: The knowledge value
        time_sensitive: Whether to apply confidence decay (default false)
        source: Entry source, "human" or "agent" (default "agent")
        confidence: Confidence for a new entry (default 1.0)

    Output:
        - entry_id: ID of the stored entry (empty on contradiction or degraded)
        - contradiction: bool indicating a contradiction was found
        - existing_value: value of the conflicting entry (empty if no contradiction)
        - proposed_value: the value that was not stored (same as value on contradiction)

    Routes:
        - "stored": entry was created or refreshed
        - "contradiction": a conflicting value was found; the caller should resolve
    """

    description = "Store a knowledge entry with automatic contradiction detection."

    inputs = [
        ParameterDef(
            name="category", type="string", description="Knowledge category", required=True
        ),
        ParameterDef(name="key", type="string", description="Knowledge key", required=True),
        ParameterDef(name="value", type="string", description="Knowledge value", required=True),
        ParameterDef(
            name="time_sensitive",
            type="bool",
            description="Whether this entry decays over time",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="source",
            type="string",
            description="Source of the knowledge ('human' or 'agent')",
            required=False,
            default="agent",
        ),
        ParameterDef(
            name="confidence",
            type="float",
            description="Confidence for a new entry (default 1.0)",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(name="entry_id", type="string", description="Stored entry ID", required=True),
        ParameterDef(
            name="contradiction",
            type="bool",
            description="Whether a contradiction was detected",
            required=True,
        ),
        ParameterDef(
            name="existing_value",
            type="string",
            description="Existing value when contradiction found",
            required=True,
        ),
        ParameterDef(
            name="proposed_value",
            type="string",
            description="Proposed value that was not stored",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        knowledge_store = context.extras.get("__knowledge_store__")
        if knowledge_store is None:
            logger.info("AddKnowledgeAction: no knowledge store — skipping")
            return TaskResult(
                success=True,
                output={
                    "entry_id": "",
                    "contradiction": False,
                    "existing_value": "",
                    "proposed_value": "",
                },
                next_route="stored",
            )

        user_id = context.get_process_property("__user_id__")
        if user_id is None:
            logger.info("AddKnowledgeAction: no user_id — skipping")
            return TaskResult(
                success=True,
                output={
                    "entry_id": "",
                    "contradiction": False,
                    "existing_value": "",
                    "proposed_value": "",
                },
                next_route="stored",
            )

        category = task.properties.get("category", "")
        key = task.properties.get("key", "")
        value = task.properties.get("value", "")
        time_sensitive = task.properties.get("time_sensitive", False)
        source = task.properties.get("source", "agent")
        confidence = task.properties.get("confidence")

        try:
            outcome = await store_knowledge_entry(
                knowledge_store,
                user_id=user_id,
                category=category,
                key=key,
                value=value,
                source=source,
                time_sensitive=time_sensitive,
                confidence=float(confidence) if confidence not in (None, "") else None,
            )
            contradiction = outcome["status"] == "contradiction"
            return TaskResult(
                success=True,
                output={
                    "entry_id": outcome["entry_id"],
                    "contradiction": contradiction,
                    "existing_value": outcome["existing_value"] if contradiction else "",
                    "proposed_value": value if contradiction else "",
                },
                next_route="contradiction" if contradiction else "stored",
            )

        except Exception as e:
            logger.warning("AddKnowledgeAction failed — degrading gracefully: %s", e)
            return TaskResult(
                success=True,
                output={
                    "entry_id": "",
                    "contradiction": False,
                    "existing_value": "",
                    "proposed_value": "",
                },
                next_route="stored",
            )

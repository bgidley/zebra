"""AddKnowledgeAction — store a knowledge entry with contradiction detection."""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


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
        from datetime import UTC, datetime

        from zebra_agent.knowledge import KnowledgeEntry

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

        try:
            existing = await knowledge_store.find_contradicting_entry(user_id, category, key)

            if existing is not None:
                if existing.value == value:
                    # Same value — just refresh last_verified and confidence
                    existing.last_verified = datetime.now(UTC)
                    existing.confidence = 1.0
                    await knowledge_store.update_entry(existing)
                    logger.info("AddKnowledgeAction: refreshed existing entry %s", existing.id)
                    return TaskResult(
                        success=True,
                        output={
                            "entry_id": existing.id,
                            "contradiction": False,
                            "existing_value": "",
                            "proposed_value": "",
                        },
                        next_route="stored",
                    )
                else:
                    # Different value — contradiction
                    logger.info(
                        "AddKnowledgeAction: contradiction for key %r (existing=%r proposed=%r)",
                        key,
                        existing.value,
                        value,
                    )
                    return TaskResult(
                        success=True,
                        output={
                            "entry_id": existing.id,
                            "contradiction": True,
                            "existing_value": existing.value,
                            "proposed_value": value,
                        },
                        next_route="contradiction",
                    )

            # No existing entry — create new
            entry = KnowledgeEntry.create(
                user_id=user_id,
                category=category,
                key=key,
                value=value,
                source=source,
                time_sensitive=time_sensitive,
            )
            await knowledge_store.add_entry(entry)
            logger.info("AddKnowledgeAction: stored new entry %s", entry.id)
            return TaskResult(
                success=True,
                output={
                    "entry_id": entry.id,
                    "contradiction": False,
                    "existing_value": "",
                    "proposed_value": "",
                },
                next_route="stored",
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

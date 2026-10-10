"""StoreLearnedKnowledgeAction — store agent-extracted knowledge candidates (F152).

Takes the candidates produced by ``extract_knowledge`` and stores each one with
the same rules as ``add_knowledge`` (``store_knowledge_entry``), as
``source="agent"`` with confidence capped below 1.0. A candidate that conflicts
with an existing entry is never written: it starts a *Resolve Knowledge
Contradiction* process so the user decides.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.knowledge.add import store_knowledge_entry
from zebra_tasks.knowledge.extract import resolve_raw, validate_candidates

logger = logging.getLogger(__name__)

RESOLVE_WORKFLOW = "Resolve Knowledge Contradiction"
CONTRADICTION_MARKER = "__knowledge_contradiction__"
DEFAULT_MAX_CONFIDENCE = 0.5
DEFAULT_MAX_ENTRIES = 5


class StoreLearnedKnowledgeAction(TaskAction):
    """Store agent-learned knowledge candidates; route conflicts to the user.

    Per candidate (at most ``max_entries``):

    - new key: stored with ``source="agent"`` and
      ``confidence = min(candidate confidence, max_confidence)``;
    - same value already stored: ``last_verified`` refreshed (confidence never
      raised to 1.0 by the agent);
    - different value already stored (human or agent): nothing is written; a
      *Resolve Knowledge Contradiction* process is started for the user, unless an
      identical one is already waiting;
    - with ``update_agent_entries`` (F155), a different value over an existing
      ``source="agent"`` entry updates that entry in place instead (e.g. a developing
      news story); conflicts with human entries still go to the user.

    Skips when there is no ``__user_id__`` or no ``__knowledge_store__``. Never
    fails the workflow.
    """

    description = "Store agent-learned knowledge; start contradiction resolution for conflicts."

    inputs = [
        ParameterDef(
            name="candidates",
            type="list",
            description="Candidates from extract_knowledge (list or template)",
            required=True,
        ),
        ParameterDef(
            name="max_confidence",
            type="float",
            description="Upper bound on stored confidence for agent entries",
            required=False,
            default=DEFAULT_MAX_CONFIDENCE,
        ),
        ParameterDef(
            name="max_entries",
            type="int",
            description="Maximum candidates stored per run",
            required=False,
            default=DEFAULT_MAX_ENTRIES,
        ),
        ParameterDef(
            name="update_agent_entries",
            type="bool",
            description="Update a conflicting agent-sourced entry in place (F155)",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="learned_knowledge",
        ),
    ]

    outputs = [
        ParameterDef(name="stored", type="list", description="Newly created entries"),
        ParameterDef(name="refreshed", type="list", description="Re-observed entries"),
        ParameterDef(name="updated", type="list", description="Agent entries updated in place"),
        ParameterDef(
            name="contradictions",
            type="list",
            description="Conflicts sent to the user, with the resolution process id",
        ),
        ParameterDef(name="skipped", type="string", description="Why nothing was stored"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        props = task.properties
        output_key = props.get("output_key", "learned_knowledge")
        result: dict[str, Any] = {
            "stored": [],
            "refreshed": [],
            "updated": [],
            "contradictions": [],
            "errors": [],
            "skipped": "",
        }

        def _finish(skipped: str = "") -> TaskResult:
            result["skipped"] = skipped
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        store = context.extras.get("__knowledge_store__")
        if store is None:
            logger.info("StoreLearnedKnowledgeAction: no knowledge store — skipping")
            return _finish("no_store")
        user_id = context.get_process_property("__user_id__")
        if user_id in (None, ""):
            logger.info("StoreLearnedKnowledgeAction: no user_id — skipping")
            return _finish("no_user")

        raw = resolve_raw(context, props.get("candidates", []))
        max_entries = int(props.get("max_entries", DEFAULT_MAX_ENTRIES))
        max_confidence = float(props.get("max_confidence", DEFAULT_MAX_CONFIDENCE))
        update_agent_entries = props.get("update_agent_entries", False) in (True, "true", "True")
        # Re-validate: candidates may come from any caller, not just extract_knowledge.
        candidates, _ = validate_candidates(
            raw if isinstance(raw, (list, dict)) else [],
            max_entries=max_entries,
            min_confidence=0.0,
            allow_sensitive=True,  # the sensitivity decision belongs to the extractor
        )
        if not candidates:
            return _finish("no_candidates")

        for c in candidates:
            confidence = min(c["confidence"], max_confidence)
            try:
                outcome = await store_knowledge_entry(
                    store,
                    user_id=user_id,
                    category=c["category"],
                    key=c["key"],
                    value=c["value"],
                    source="agent",
                    time_sensitive=c["time_sensitive"],
                    confidence=confidence,
                )
            except Exception as e:
                logger.warning("StoreLearnedKnowledgeAction: store failed for %s: %s", c["key"], e)
                result["errors"].append({"key": c["key"], "error": str(e)[:200]})
                continue

            summary = {
                "entry_id": outcome["entry_id"],
                "category": c["category"],
                "key": c["key"],
                "value": c["value"],
            }
            if outcome["status"] == "created":
                result["stored"].append({**summary, "confidence": confidence})
            elif outcome["status"] == "refreshed":
                result["refreshed"].append(summary)
            elif (
                update_agent_entries
                and outcome["existing_source"] == "agent"
                and await self._update_in_place(store, outcome["entry_id"], c, confidence)
            ):
                result["updated"].append({**summary, "previous_value": outcome["existing_value"]})
            else:
                process_id = await self._start_resolution(
                    context, user_id, c, outcome["entry_id"], outcome["existing_value"]
                )
                result["contradictions"].append(
                    {
                        **summary,
                        "existing_value": outcome["existing_value"],
                        "existing_source": outcome["existing_source"],
                        "resolution_process_id": process_id,
                    }
                )

        logger.info(
            "StoreLearnedKnowledgeAction: stored=%d refreshed=%d updated=%d contradictions=%d",
            len(result["stored"]),
            len(result["refreshed"]),
            len(result["updated"]),
            len(result["contradictions"]),
        )
        return _finish()

    @staticmethod
    async def _update_in_place(
        store: Any, entry_id: str, candidate: dict[str, Any], confidence: float
    ) -> bool:
        """Overwrite an agent-sourced entry with a newer agent observation; True if done."""
        try:
            entry = await store.get_entry(entry_id)
            if entry is None or entry.source != "agent":
                return False
            now = datetime.now(UTC)
            entry.value = candidate["value"]
            entry.confidence = confidence
            entry.time_sensitive = candidate["time_sensitive"]
            entry.last_verified = now
            entry.updated_at = now
            await store.update_entry(entry)
            return True
        except Exception as e:
            logger.warning("StoreLearnedKnowledgeAction: in-place update failed: %s", e)
            return False

    async def _start_resolution(
        self,
        context: ExecutionContext,
        user_id: Any,
        candidate: dict[str, Any],
        entry_id: str,
        existing_value: str,
    ) -> str:
        """Start a Resolve Knowledge Contradiction process; return its id ("" if not started)."""
        marker = f"{entry_id}:{candidate['value']}"
        try:
            for proc in await context.store.get_processes_by_state(ProcessState.RUNNING):
                if (proc.properties or {}).get(CONTRADICTION_MARKER) == marker:
                    logger.info("Contradiction for %s already awaiting the user", entry_id)
                    return proc.id

            library = context.extras.get("__workflow_library__")
            if library is None:
                logger.warning("StoreLearnedKnowledgeAction: no workflow library — not resolving")
                return ""
            definition = library.get_workflow(RESOLVE_WORKFLOW)
            process = await context.engine.create_process(
                definition,
                properties={
                    "__user_id__": user_id,
                    "entry_id": entry_id,
                    "category": candidate["category"],
                    "key": candidate["key"],
                    "existing_value": existing_value,
                    "proposed_value": candidate["value"],
                    "source_process_id": context.process.id,
                    CONTRADICTION_MARKER: marker,
                },
            )
            await context.engine.start_process(process.id)
            logger.info(
                "StoreLearnedKnowledgeAction: contradiction on %s → process %s",
                candidate["key"],
                process.id,
            )
            return process.id
        except Exception as e:
            logger.warning("StoreLearnedKnowledgeAction: could not start resolution: %s", e)
            return ""

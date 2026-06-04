"""Data export service for Zebra Agent.

Produces a portable ZIP archive containing all user data:
- processes.json  — all process instances and their tasks
- memory.json     — episodic (workflow) + conceptual memory entries
- metrics.json    — workflow run records
- knowledge.json  — personal knowledge entries
- manifest.json   — format version, user_id, export timestamp
- workflows/      — user YAML workflow files

Format version: 1
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebra_agent.storage.interfaces import MemoryStore, MetricsStore, PersonalKnowledgeStore

logger = logging.getLogger(__name__)

# Increment when the archive format changes in a backward-incompatible way.
EXPORT_FORMAT_VERSION = 1


class DataExporter:
    """Assembles a portable ZIP export of all user data.

    The archive layout is deterministic and documented in specs/f9-data-export.md.
    Each call to export_user_data() produces a fresh, self-contained snapshot.
    """

    async def export_user_data(
        self,
        user_id: str | int,
        memory_store: MemoryStore | None = None,
        metrics_store: MetricsStore | None = None,
        knowledge_store: PersonalKnowledgeStore | None = None,
        process_store: Any = None,
        workflow_library: Any = None,
    ) -> bytes:
        """Build a ZIP archive of all data for the given user.

        Args:
            user_id: The user whose data to export.
            memory_store: Optional MemoryStore to export workflow/conceptual memory.
            metrics_store: Optional MetricsStore to export run metrics.
            knowledge_store: Optional PersonalKnowledgeStore to export knowledge entries.
            process_store: Optional StateStore to export process instances.
            workflow_library: Optional WorkflowLibrary to export YAML workflow files.

        Returns:
            ZIP archive as raw bytes.
        """
        exported_at = datetime.now(UTC).isoformat()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest: dict[str, Any] = {
                "format_version": EXPORT_FORMAT_VERSION,
                "user_id": str(user_id),
                "exported_at": exported_at,
                "sections": [],
            }

            # processes.json
            processes_data = await self._export_processes(user_id, process_store)
            zf.writestr("processes.json", _to_json(processes_data))
            manifest["sections"].append("processes")

            # memory.json
            memory_data = await self._export_memory(memory_store)
            zf.writestr("memory.json", _to_json(memory_data))
            manifest["sections"].append("memory")

            # metrics.json
            metrics_data = await self._export_metrics(metrics_store)
            zf.writestr("metrics.json", _to_json(metrics_data))
            manifest["sections"].append("metrics")

            # knowledge.json
            knowledge_data = await self._export_knowledge(user_id, knowledge_store)
            zf.writestr("knowledge.json", _to_json(knowledge_data))
            manifest["sections"].append("knowledge")

            # workflows/ directory
            workflow_count = await self._export_workflows(zf, workflow_library)
            if workflow_count > 0:
                manifest["sections"].append("workflows")

            zf.writestr("manifest.json", _to_json(manifest))

        logger.info("Exported data for user %s: %d bytes", user_id, buf.tell())
        return buf.getvalue()

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _export_processes(self, user_id: str | int, process_store: Any) -> dict:
        """Export process instances and their tasks."""
        if process_store is None:
            logger.debug("No process_store — skipping processes export")
            return {"processes": [], "note": "no_process_store"}

        try:
            processes = await process_store.list_processes(include_completed=True)
            result = []
            for p in processes:
                p_dict = _model_to_dict(p)
                try:
                    tasks = await process_store.load_tasks_for_process(p.id)
                    p_dict["tasks"] = [_model_to_dict(t) for t in tasks]
                except Exception as exc:
                    logger.warning("Could not load tasks for process %s: %s", p.id, exc)
                    p_dict["tasks"] = []
                result.append(p_dict)
            return {"processes": result}
        except Exception as exc:
            logger.warning("Failed to export processes: %s", exc)
            return {"processes": [], "error": str(exc)}

    async def _export_memory(self, memory_store: MemoryStore | None) -> dict:
        """Export workflow memory and conceptual memory."""
        if memory_store is None:
            return {"workflow_memories": [], "conceptual_memories": [], "note": "no_memory_store"}

        try:
            workflow_memories = await memory_store.get_recent_workflow_memories(limit=10_000)
            conceptual_memories = await memory_store.get_conceptual_memories(limit=10_000)
            return {
                "workflow_memories": [e.to_dict() for e in workflow_memories],
                "conceptual_memories": [e.to_dict() for e in conceptual_memories],
            }
        except Exception as exc:
            logger.warning("Failed to export memory: %s", exc)
            return {"workflow_memories": [], "conceptual_memories": [], "error": str(exc)}

    async def _export_metrics(self, metrics_store: MetricsStore | None) -> dict:
        """Export workflow run records."""
        if metrics_store is None:
            return {"runs": [], "note": "no_metrics_store"}

        try:
            runs = await metrics_store.get_recent_runs(limit=100_000)
            runs_data = []
            for r in runs:
                run_dict = {
                    "id": r.id,
                    "workflow_name": r.workflow_name,
                    "goal": r.goal,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "success": r.success,
                    "user_rating": r.user_rating,
                    "tokens_used": r.tokens_used,
                    "cost": float(r.cost) if r.cost is not None else 0.0,
                    "error": r.error,
                    "output": str(r.output) if r.output is not None else None,
                    "model": r.model,
                }
                runs_data.append(run_dict)
            return {"runs": runs_data}
        except Exception as exc:
            logger.warning("Failed to export metrics: %s", exc)
            return {"runs": [], "error": str(exc)}

    async def _export_knowledge(
        self, user_id: str | int, knowledge_store: PersonalKnowledgeStore | None
    ) -> dict:
        """Export personal knowledge entries."""
        if knowledge_store is None:
            return {"entries": [], "note": "no_knowledge_store"}

        try:
            entries = await knowledge_store.get_entries(user_id=int(user_id), include_deleted=True)
            return {
                "entries": [
                    {
                        "id": e.id,
                        "user_id": e.user_id,
                        "category": e.category,
                        "key": e.key,
                        "value": e.value,
                        "source": e.source,
                        "confidence": e.confidence,
                        "last_verified": e.last_verified.isoformat(),
                        "created_at": e.created_at.isoformat(),
                        "updated_at": e.updated_at.isoformat(),
                        "time_sensitive": e.time_sensitive,
                        "deleted_at": e.deleted_at.isoformat() if e.deleted_at else None,
                    }
                    for e in entries
                ]
            }
        except Exception as exc:
            logger.warning("Failed to export knowledge: %s", exc)
            return {"entries": [], "error": str(exc)}

    async def _export_workflows(self, zf: zipfile.ZipFile, workflow_library: Any) -> int:
        """Write YAML workflow files into the workflows/ directory in the ZIP."""
        if workflow_library is None:
            return 0

        count = 0
        try:
            workflows = await workflow_library.list_workflows()
            for wf in workflows:
                try:
                    yaml_content = workflow_library.get_workflow_yaml(wf.name)
                    # Sanitise name for use as filename
                    safe_name = wf.name.replace("/", "_").replace("\\", "_")
                    zf.writestr(f"workflows/{safe_name}.yaml", yaml_content)
                    count += 1
                except Exception as exc:
                    logger.warning("Could not export workflow %r: %s", wf.name, exc)
        except Exception as exc:
            logger.warning("Failed to list workflows for export: %s", exc)

        return count


# =============================================================================
# Helpers
# =============================================================================


def _to_json(obj: Any) -> str:
    """Serialise obj to a pretty-printed JSON string."""
    return json.dumps(obj, indent=2, default=_json_default)


def _json_default(obj: Any) -> Any:
    """JSON serialisation fallback for datetime and Pydantic models."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.asdict(obj)
    return str(obj)


def _model_to_dict(obj: Any) -> dict:
    """Convert a Pydantic model or dataclass to a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.asdict(obj)
    return dict(obj)

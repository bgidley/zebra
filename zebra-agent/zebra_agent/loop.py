"""Main agent loop - orchestrates workflow selection, execution, and learning.

This module implements the agent loop as a Zebra workflow. The AgentLoop class
is a thin wrapper that runs the "Agent Main Loop" workflow, which handles:
1. Memory compaction check
2. Workflow selection via LLM
3. Workflow creation (if needed)
4. Workflow execution
5. Metrics recording
6. Memory updates
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState

from zebra_agent.library import WorkflowLibrary
from zebra_agent.storage.interfaces import MemoryStore, MetricsStore

# Type for progress callback: receives event name and data dict
ProgressCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class AgentResult:
    """Result of processing a goal."""

    run_id: str
    workflow_name: str
    goal: str
    output: Any
    success: bool
    tokens_used: int = 0
    error: str | None = None
    created_new_workflow: bool = False


class AgentLoop:
    """
    Main agent loop: select → run → evaluate → learn.

    This class orchestrates goal processing by running the "Agent Main Loop"
    workflow, which declaratively handles all steps of the agent loop.

    The workflow-based approach ensures:
    - Each step is a composable subworkflow
    - Steps can be individually tested and modified
    - The loop logic is visible and editable as YAML
    - Progress tracking is built into the workflow engine
    """

    def __init__(
        self,
        library: WorkflowLibrary,
        engine: WorkflowEngine,
        metrics: MetricsStore,
        memory: MemoryStore | None = None,
        provider: str = "anthropic",
        model: str | None = None,
    ):
        """
        Initialize the agent loop.

        Args:
            library: Workflow library for loading/storing workflows
            engine: Zebra workflow engine for execution
            metrics: Metrics store for recording run history
            memory: Agent memory store for context (optional)
            provider: LLM provider name
            model: LLM model name (optional)
        """
        self.library = library
        self.engine = engine
        self.metrics = metrics
        self.memory = memory
        self.provider_name = provider
        self.model = model

        # Inject stores into engine extras for task actions to use
        # These are non-serializable objects that can't go in process properties
        self.engine.extras["__memory_store__"] = memory
        self.engine.extras["__metrics_store__"] = metrics
        self.engine.extras["__workflow_library__"] = library

    async def process_goal(
        self,
        goal: str,
        progress_callback: ProgressCallback | None = None,
        run_id: str | None = None,
        model: str | None = None,
        user_id: int | None = None,
    ) -> AgentResult:
        """
        Process a user goal through the agent loop workflow.

        Runs the "Agent Main Loop" workflow which handles:
        1. Check if memory needs compaction (runs compaction subworkflows if needed)
        2. Select best workflow for the goal using LLM
        3. Create new workflow if no good match exists
        4. Execute the selected/created workflow
        5. Record metrics for the run
        6. Update agent memory with the interaction

        Args:
            goal: The user's goal/request
            progress_callback: Optional async callback for progress updates.
                Called with (event_name, data_dict) at key points.
            run_id: Optional run ID to use (for tracking from external callers)

        Returns:
            AgentResult with output, success status, tokens used, etc.

        Raises:
            ValueError: If the "Agent Main Loop" workflow is not found
        """
        run_id = run_id or str(uuid.uuid4())

        async def emit(event: str, data: dict[str, Any] | None = None) -> None:
            """Emit progress event if callback is provided."""
            if progress_callback:
                await progress_callback(event, data or {})

        # Load the main agent loop workflow
        definition = self.library.get_workflow("Agent Main Loop")

        # Prepare available workflows for the selector (exclude system workflows)
        workflows = await self.library.list_workflows()
        available_workflows = [
            {
                "name": w.name,
                "description": w.description,
                "tags": w.tags,
                "success_rate": w.success_rate,
                "use_count": w.use_count,
                "use_when": w.use_when,
            }
            for w in workflows
            if not self._is_system_workflow(w.name)
        ]

        # Prepare initial properties for the workflow
        # Note: Stores are passed via engine.extras (set in __init__) since they're
        # not JSON-serializable and can't be stored in process properties.
        properties = {
            "goal": goal,
            "run_id": run_id,
            "available_workflows": available_workflows,
            "__llm_provider_name__": self.provider_name,
            "__llm_model__": model or self.model,
            "__started_at__": datetime.now(UTC).isoformat(),
            "__user_id__": user_id,
        }

        await emit("started", {"run_id": run_id, "goal": goal})

        # Store progress callback in engine extras so task actions can emit events.
        # This is the same pattern used for __memory_store__, __metrics_store__, etc.
        if progress_callback:
            self.engine.extras["__progress_callback__"] = progress_callback

        try:
            execution_result = await self._run_agent_workflow(definition, properties, goal, run_id)
        finally:
            # Clean up callback to avoid stale references between runs
            self.engine.extras.pop("__progress_callback__", None)

        return AgentResult(
            run_id=run_id,
            workflow_name=execution_result.get("workflow_name", "unknown"),
            goal=goal,
            output=execution_result.get("output"),
            success=execution_result.get("success", False),
            tokens_used=execution_result.get("tokens_used", 0),
            error=execution_result.get("error"),
            created_new_workflow=execution_result.get("created_new", False),
        )

    async def _run_agent_workflow(
        self,
        definition: Any,
        properties: dict[str, Any],
        goal: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Run the agent main loop workflow and wait for completion.

        Returns:
            Dict with execution_result and metadata from process properties.
        """
        # Create and run the main loop workflow
        process = await self.engine.create_process(definition, properties=properties)
        await self.engine.start_process(process.id)

        # Wait for completion with progress tracking
        max_wait = 300  # 5 minutes for the full loop
        waited = 0.0

        while waited < max_wait:
            process = await self.engine.store.load_process(process.id)

            if process.state == ProcessState.COMPLETE:
                break
            elif process.state == ProcessState.FAILED:
                error = process.properties.get("__error__", "Workflow failed")
                return {
                    "workflow_name": process.properties.get("workflow_name", "unknown"),
                    "output": None,
                    "success": False,
                    "tokens_used": 0,
                    "error": str(error),
                    "created_new": process.properties.get("created_new", False),
                }

            await asyncio.sleep(0.5)
            waited += 0.5

        if process.state != ProcessState.COMPLETE:
            return {
                "workflow_name": process.properties.get("workflow_name", "unknown"),
                "output": None,
                "success": False,
                "tokens_used": 0,
                "error": "Agent loop timed out",
            }

        # Extract results from process properties
        execution_result = process.properties.get("execution_result", {})

        return {
            "workflow_name": process.properties.get("workflow_name", "unknown"),
            "output": execution_result.get("output"),
            "success": execution_result.get("success", False),
            "tokens_used": execution_result.get("tokens_used", 0),
            "created_new": process.properties.get("created_new", False),
        }

    async def record_rating(self, run_id: str, rating: int) -> None:
        """Record a user rating for a run."""
        await self.metrics.update_rating(run_id, rating)

    async def record_feedback(self, run_id: str, feedback: str) -> bool:
        """Record user feedback on the workflow memory entry for a run.

        Returns True if a matching memory entry was found and updated.
        """
        if self.memory is None:
            return False
        return await self.memory.update_user_feedback(run_id, feedback)

    async def run_dream_cycle(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """
        Run the Dream Cycle self-improvement workflow.

        Analyzes recent performance metrics, evaluates workflow effectiveness,
        and optimizes or creates workflows based on the evaluation.

        Unlike ``process_goal()``, this runs the "Dream Cycle" workflow
        directly — it does not go through the goal-selection step.

        Args:
            progress_callback: Optional async callback for progress updates.

        Returns:
            Dict with dream cycle results including dream_summary,
            metrics_analysis, evaluation, and optimization_results.

        Raises:
            ValueError: If the "Dream Cycle" workflow is not found.
        """
        run_id = str(uuid.uuid4())

        async def emit(event: str, data: dict[str, Any] | None = None) -> None:
            if progress_callback:
                await progress_callback(event, data or {})

        definition = self.library.get_workflow("Dream Cycle")

        properties = {
            "__llm_provider_name__": self.provider_name,
            "__llm_model__": self.model,
            "__started_at__": datetime.now(UTC).isoformat(),
            # The optimizer needs the library path for saving modified workflows
            "__workflow_library_path__": str(self.library.library_path),
        }

        await emit("dream_cycle_started", {"run_id": run_id})

        if progress_callback:
            self.engine.extras["__progress_callback__"] = progress_callback

        try:
            process = await self.engine.create_process(definition, properties=properties)
            await self.engine.start_process(process.id)

            # Dream cycles may take longer than regular goals
            max_wait = 600  # 10 minutes
            waited = 0.0

            while waited < max_wait:
                process = await self.engine.store.load_process(process.id)

                if process.state == ProcessState.COMPLETE:
                    break
                elif process.state == ProcessState.FAILED:
                    error = process.properties.get("__error__", "Dream cycle failed")
                    await emit("dream_cycle_failed", {"run_id": run_id, "error": str(error)})
                    return {
                        "success": False,
                        "error": str(error),
                    }

                await asyncio.sleep(1.0)
                waited += 1.0

            if process.state != ProcessState.COMPLETE:
                await emit("dream_cycle_failed", {"run_id": run_id, "error": "Timed out"})
                return {
                    "success": False,
                    "error": "Dream cycle timed out",
                }

            await emit("dream_cycle_completed", {"run_id": run_id})

            return {
                "success": True,
                "dream_summary": process.properties.get("dream_summary"),
                "metrics_analysis": process.properties.get("metrics_analysis"),
                "evaluation": process.properties.get("evaluation"),
                "optimization_results": process.properties.get("optimization_results"),
            }

        finally:
            self.engine.extras.pop("__progress_callback__", None)

    def _is_system_workflow(self, name: str) -> bool:
        """Check if a workflow is a system/internal workflow."""
        system_workflows = {
            "Agent Main Loop",
            "Dream Cycle",
            "Create Goal",
        }
        return name in system_workflows

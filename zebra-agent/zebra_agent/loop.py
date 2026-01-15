"""Main agent loop - select, execute, and learn from workflows."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

from zebra_agent.library import WorkflowLibrary
from zebra_agent.memory import (
    AgentMemory,
    LongTermTheme,
    MemoryEntry,
    ShortTermSummary,
    estimate_tokens,
)
from zebra_agent.metrics import MetricsStore, WorkflowRun


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


@dataclass
class WorkflowSelection:
    """Result of workflow selection."""

    workflow_name: str | None
    create_new: bool
    reasoning: str
    suggested_name: str | None = None


class AgentLoop:
    """
    Main agent loop: select → run → evaluate → learn.

    This class orchestrates the workflow selection and execution process.
    """

    SELECTOR_SYSTEM_PROMPT = """You are a workflow selector. Given a user goal and available workflows,
select the best match or recommend creating a new one.

Consider:
- How well the workflow description matches the goal
- The workflow's success rate (higher is better)
- Whether the goal requires capabilities the workflow provides

Respond with JSON only:
{
    "workflow_name": "name of selected workflow" or null if creating new,
    "create_new": true if no good match exists,
    "reasoning": "brief explanation of your choice",
    "suggested_name": "name for new workflow" (only if create_new is true)
}"""

    CREATOR_SYSTEM_PROMPT = """You are a workflow designer for the Zebra workflow engine.
Create workflow definitions in YAML format.

## Workflow Structure

```yaml
name: "Workflow Name"
description: "What this workflow does"
tags: ["tag1", "tag2"]
version: 1
first_task: task_id

tasks:
  task_id:
    name: "Task Display Name"
    action: llm_call
    auto: true
    properties:
      system_prompt: "Instructions for the LLM"
      prompt: "{{goal}}"
      output_key: result_name

routings:
  - from: task1_id
    to: task2_id
```

## Available Actions

- **llm_call**: Call an LLM with a prompt
  - Properties: system_prompt, prompt, output_key, temperature, max_tokens
  - Use {{variable}} to reference process properties or previous outputs

## Guidelines

1. Use descriptive task IDs
2. Always include description and tags
3. Use {{goal}} to reference the user's input
4. Use {{previous_output_key}} to chain task outputs
5. Keep workflows focused

Output ONLY valid YAML, no explanations."""

    def __init__(
        self,
        library: WorkflowLibrary,
        engine: WorkflowEngine,
        metrics: MetricsStore,
        memory: AgentMemory | None = None,
        provider: str = "anthropic",
        model: str | None = None,
    ):
        """
        Initialize the agent loop.

        Args:
            library: Workflow library
            engine: Zebra workflow engine
            metrics: Metrics store
            memory: Agent memory for context (optional)
            provider: LLM provider name
            model: LLM model name (optional)
        """
        self.library = library
        self.engine = engine
        self.metrics = metrics
        self.memory = memory
        self.provider_name = provider
        self.model = model
        self._llm = None

    @property
    def llm(self):
        """Lazily initialize LLM provider."""
        if self._llm is None:
            self._llm = get_provider(self.provider_name, self.model)
        return self._llm

    async def process_goal(self, goal: str) -> AgentResult:
        """
        Process a user goal through the agent loop.

        1. Check if memory needs compaction
        2. Select or create workflow for goal
        3. Execute workflow
        4. Record result and update memory

        Args:
            goal: The user's goal/request

        Returns:
            AgentResult with output, success status, etc.
        """
        # Check if memory needs compaction first
        if self.memory:
            if await self.memory.needs_short_term_compaction():
                await self._compact_short_term_memory()
            if await self.memory.needs_long_term_compaction():
                await self._compact_long_term_memory()

        # Create run record
        run = WorkflowRun.create("pending", goal)
        created_new = False

        try:
            # Step 1: Select workflow
            selection = await self._select_workflow(goal)

            if selection.create_new:
                # Step 1b: Create new workflow
                workflow_name = await self._create_workflow(
                    goal, selection.suggested_name
                )
                created_new = True
            else:
                workflow_name = selection.workflow_name

            run.workflow_name = workflow_name

            # Step 2: Execute workflow
            output, tokens = await self._execute_workflow(workflow_name, goal)

            # Step 3: Record success
            run.completed_at = datetime.now()
            run.success = True
            run.tokens_used = tokens
            run.output = output

            await self.metrics.record_run(run)

            # Step 4: Update memory
            if self.memory:
                await self._add_to_memory(run, output)

            return AgentResult(
                run_id=run.id,
                workflow_name=workflow_name,
                goal=goal,
                output=output,
                success=True,
                tokens_used=tokens,
                created_new_workflow=created_new,
            )

        except Exception as e:
            # Record failure
            run.completed_at = datetime.now()
            run.success = False
            run.error = str(e)

            await self.metrics.record_run(run)

            # Still add to memory on failure
            if self.memory:
                await self._add_to_memory(run, f"Error: {e}")

            return AgentResult(
                run_id=run.id,
                workflow_name=run.workflow_name,
                goal=goal,
                output=None,
                success=False,
                error=str(e),
                created_new_workflow=created_new,
            )

    async def _select_workflow(self, goal: str) -> WorkflowSelection:
        """Use LLM to select the best workflow for the goal."""
        workflows = await self.library.list_workflows()

        # Build prompt
        prompt = f"Goal: {goal}\n\n"

        if workflows:
            prompt += "Available workflows:\n"
            for w in workflows:
                tags_str = ", ".join(w.tags) if w.tags else "none"
                success = f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A"
                prompt += f"- {w.name}: {w.description} (success: {success}, tags: {tags_str})\n"
                if w.use_when:
                    prompt += f"  USE WHEN: {w.use_when}\n"
        else:
            prompt += "No workflows available yet. You must create a new one.\n"

        response = await self.llm.complete(
            messages=[
                Message.system(self.SELECTOR_SYSTEM_PROMPT),
                Message.user(prompt),
            ],
            temperature=0.3,
            max_tokens=500,
        )

        # Parse response
        content = response.content or ""

        # Extract JSON from code blocks if present
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end].strip()

        data = json.loads(content)

        # Force create_new if no workflows available
        if not workflows:
            data["create_new"] = True
            data["workflow_name"] = None

        return WorkflowSelection(
            workflow_name=data.get("workflow_name"),
            create_new=data.get("create_new", False),
            reasoning=data.get("reasoning", ""),
            suggested_name=data.get("suggested_name"),
        )

    async def _create_workflow(self, goal: str, suggested_name: str | None) -> str:
        """Use LLM to create a new workflow."""
        workflows = await self.library.list_workflows()

        prompt = f"Create a workflow for: {goal}\n"

        if suggested_name:
            prompt += f"\nSuggested name: {suggested_name}\n"

        if workflows:
            prompt += "\nExisting workflows for reference:\n"
            for w in workflows[:3]:
                prompt += f"- {w.name}: {w.description}\n"

        response = await self.llm.complete(
            messages=[
                Message.system(self.CREATOR_SYSTEM_PROMPT),
                Message.user(prompt),
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        yaml_content = response.content or ""

        # Clean up - remove code blocks if present
        if "```yaml" in yaml_content:
            start = yaml_content.index("```yaml") + 7
            end = yaml_content.index("```", start)
            yaml_content = yaml_content[start:end].strip()
        elif "```yml" in yaml_content:
            start = yaml_content.index("```yml") + 6
            end = yaml_content.index("```", start)
            yaml_content = yaml_content[start:end].strip()
        elif "```" in yaml_content:
            start = yaml_content.index("```") + 3
            end = yaml_content.index("```", start)
            yaml_content = yaml_content[start:end].strip()

        # Add to library (validates YAML)
        return self.library.add_workflow(yaml_content)

    async def _execute_workflow(self, workflow_name: str, goal: str) -> tuple[Any, int]:
        """
        Execute a workflow and return the output.

        Returns:
            Tuple of (output, tokens_used)
        """
        # Load workflow
        definition = self.library.get_workflow(workflow_name)

        # Create process with goal as property
        process = await self.engine.create_process(
            definition,
            properties={
                "goal": goal,
                "__llm_provider_name__": self.provider_name,
                "__llm_model__": self.model,
            },
        )

        # Start and run to completion
        await self.engine.start_process(process.id)

        # Wait for completion (simple polling for now)
        import asyncio

        max_wait = 120  # 2 minutes max
        waited = 0

        while waited < max_wait:
            process = await self.engine.store.load_process(process.id)

            if process.state == ProcessState.COMPLETE:
                break
            elif process.state == ProcessState.FAILED:
                raise RuntimeError(f"Workflow failed: {process.error}")

            await asyncio.sleep(0.5)
            waited += 0.5

        if process.state != ProcessState.COMPLETE:
            raise RuntimeError("Workflow timed out")

        # Get output from process properties
        # Try common output keys
        output = None
        for key in [
            "answer",
            "summary",
            "ideas",
            "refined_ideas",
            "solutions",
            "result",
            "output",
        ]:
            if key in process.properties:
                output = process.properties[key]
                break

        # Fall back to all properties if no standard key found
        if output is None:
            output = {
                k: v
                for k, v in process.properties.items()
                if not k.startswith("__")
            }

        # Get token usage
        tokens = process.properties.get("__total_tokens__", 0)

        return output, tokens

    async def record_rating(self, run_id: str, rating: int) -> None:
        """Record a user rating for a run."""
        await self.metrics.update_rating(run_id, rating)

    async def _add_to_memory(self, run: WorkflowRun, output: Any) -> None:
        """Add a workflow run to memory."""
        if not self.memory:
            return

        # Create summary of output
        if isinstance(output, str):
            summary = output[:500] + "..." if len(output) > 500 else output
        elif isinstance(output, dict):
            summary = json.dumps(output, indent=2)[:500]
        else:
            summary = str(output)[:500]

        entry = MemoryEntry(
            id=run.id,
            timestamp=run.started_at,
            goal=run.goal,
            workflow_used=run.workflow_name or "unknown",
            result_summary=summary,
            tokens=estimate_tokens(run.goal + summary),
        )

        await self.memory.add_entry(entry)

    async def _compact_short_term_memory(self) -> None:
        """
        Compact short-term memory into a detailed summary.

        Focuses on preserving specific details, facts, and outcomes.
        """
        if not self.memory:
            return

        import asyncio
        import uuid

        # Get short-term content for compaction
        memory_content = await self.memory.get_short_term_content_for_compaction()
        if not memory_content:
            return

        # Count entries being compacted
        entries = await self.memory.get_short_term_entries()
        entry_count = len(entries)

        # Load and run the short-term compact workflow
        try:
            definition = self.library.get_workflow("Memory Compact Short")
        except KeyError:
            # Workflow not available, skip compaction
            return

        process = await self.engine.create_process(
            definition,
            properties={
                "memory_content": memory_content,
                "__llm_provider_name__": self.provider_name,
                "__llm_model__": self.model,
            },
        )

        await self.engine.start_process(process.id)

        # Wait for completion
        max_wait = 60
        waited = 0

        while waited < max_wait:
            process = await self.engine.store.load_process(process.id)

            if process.state == ProcessState.COMPLETE:
                break
            elif process.state == ProcessState.FAILED:
                return

            await asyncio.sleep(0.5)
            waited += 0.5

        if process.state != ProcessState.COMPLETE:
            return

        # Get the summary and store it
        summary_text = process.properties.get("short_term_summary")
        if summary_text:
            summary = ShortTermSummary(
                id=str(uuid.uuid4()),
                created_at=datetime.now(),
                summary=summary_text,
                tokens=estimate_tokens(summary_text),
                entry_count=entry_count,
            )
            await self.memory.add_short_term_summary(summary)
            await self.memory.clear_short_term_entries()

    async def _compact_long_term_memory(self) -> None:
        """
        Compact long-term memory by extracting themes from short-term summaries.

        Focuses on patterns, preferences, and high-level insights.
        References short-term summaries for detail retrieval.
        """
        if not self.memory:
            return

        import asyncio
        import uuid

        # Get long-term content for compaction
        memory_content = await self.memory.get_long_term_content_for_compaction()
        if not memory_content:
            return

        # Get IDs of summaries being processed
        summaries = await self.memory.get_short_term_summaries()
        summary_ids = [s.id for s in summaries]

        # Load and run the long-term compact workflow
        try:
            definition = self.library.get_workflow("Memory Compact Long")
        except KeyError:
            # Workflow not available, skip compaction
            return

        process = await self.engine.create_process(
            definition,
            properties={
                "memory_content": memory_content,
                "__llm_provider_name__": self.provider_name,
                "__llm_model__": self.model,
            },
        )

        await self.engine.start_process(process.id)

        # Wait for completion
        max_wait = 90  # Longer timeout for theme extraction
        waited = 0

        while waited < max_wait:
            process = await self.engine.store.load_process(process.id)

            if process.state == ProcessState.COMPLETE:
                break
            elif process.state == ProcessState.FAILED:
                return

            await asyncio.sleep(0.5)
            waited += 0.5

        if process.state != ProcessState.COMPLETE:
            return

        # Get the themes and store them
        theme_text = process.properties.get("long_term_themes")
        if theme_text:
            theme = LongTermTheme(
                id=str(uuid.uuid4()),
                created_at=datetime.now(),
                theme=theme_text,
                tokens=estimate_tokens(theme_text),
                short_term_refs=summary_ids,  # Reference the summaries used
            )
            await self.memory.add_long_term_theme(theme)
            # Keep referenced summaries but clear older ones if needed
            # For now, keep all summaries that are referenced by themes
            await self.memory.clear_short_term_summaries(keep_ids=summary_ids)

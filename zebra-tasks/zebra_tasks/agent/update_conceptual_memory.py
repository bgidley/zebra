"""UpdateConceptualMemoryAction - incremental update of the conceptual memory index."""

import json
import logging
from datetime import UTC

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)


class UpdateConceptualMemoryAction(TaskAction):
    """
    Incrementally update the conceptual memory index after a workflow run.

    This is the final step of the agent loop. It reads the recent workflow memory
    entries (including the just-recorded run), asks the LLM to produce an updated
    conceptual index entry for the relevant goal concept, and saves it back to the
    memory store.

    The update is incremental: we look up whether a matching conceptual entry
    already exists (by concept similarity), update it if so, or create a new one.
    This keeps the index compact and growing organically.

    Properties:
        workflow_name: The workflow that was just used/created
        goal: User's original goal
        success: Whether the run succeeded
        effectiveness_notes: LLM assessment from assess_and_record step
        provider: LLM provider name (default: anthropic)
        model: LLM model name (optional)
        output_key: Where to store result (default: "conceptual_memory_update")

    Output:
        - updated: bool — whether update succeeded
        - concept: the concept label that was updated/created

    Example workflow usage:
        ```yaml
        tasks:
          update_conceptual_memory:
            name: "Update Conceptual Memory"
            action: update_conceptual_memory
            auto: true
            properties:
              workflow_name: "{{workflow_name}}"
              goal: "{{goal}}"
              success: "{{execution_result.success}}"
              effectiveness_notes: "{{assess_result.effectiveness_notes}}"
              output_key: conceptual_memory_update
        ```
    """

    description = "Incrementally update conceptual memory index after a workflow run."

    inputs = [
        ParameterDef(
            name="workflow_name", type="string", description="Workflow used", required=True
        ),
        ParameterDef(name="goal", type="string", description="User's original goal", required=True),
        ParameterDef(
            name="success", type="bool", description="Whether run succeeded", required=True
        ),
        ParameterDef(
            name="effectiveness_notes",
            type="string",
            description="LLM effectiveness assessment",
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
        ParameterDef(name="model", type="string", description="LLM model name", required=False),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store result",
            required=False,
            default="conceptual_memory_update",
        ),
    ]

    outputs = [
        ParameterDef(
            name="updated", type="bool", description="Whether the update succeeded", required=True
        ),
        ParameterDef(
            name="concept",
            type="string",
            description="Concept label that was updated/created",
            required=False,
        ),
    ]

    SYSTEM_PROMPT = (
        "You are an agent that maintains a conceptual memory index for a workflow system.\n"
        "\n"
        "Given information about a recently completed workflow run and the existing conceptual\n"
        "memory, produce an updated index entry that maps this goal pattern to the recommended\n"
        "workflow(s).\n"
        "\n"
        "The conceptual memory is a compact index: each entry represents a category of goals\n"
        "and which workflows work best for them.\n"
        "\n"
        "Rules:\n"
        "1. Identify the abstract concept/category that this goal belongs to\n"
        "   (e.g. 'code analysis', 'writing assistance', 'data processing')\n"
        "2. Either update an existing concept entry (if one matches) or create a new one\n"
        "3. Keep fit_notes concise (1-2 sentences per workflow)\n"
        "4. anti_patterns should capture what does NOT work for this concept\n"
        "5. Include avg_rating if available (use null if not)\n"
        "\n"
        "Respond with JSON only:\n"
        "{\n"
        '    "concept": "short concept label (3-6 words)",\n'
        '    "recommended_workflows": [\n'
        "        {\n"
        '            "name": "workflow_name",\n'
        '            "fit_notes": "why this workflow suits this concept",\n'
        '            "avg_rating": null,\n'
        '            "use_count": 1\n'
        "        }\n"
        "    ],\n"
        '    "anti_patterns": "what types of approaches/workflows don\'t work well here"\n'
        "}"
    )

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Incrementally update conceptual memory."""
        workflow_name = self._resolve(task, context, "workflow_name", "")
        goal = self._resolve(task, context, "goal", "")
        effectiveness_notes = self._resolve(task, context, "effectiveness_notes", "")
        success = task.properties.get("success", False)
        if isinstance(success, str):
            success = success.lower() in ("true", "1", "yes")
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")
        output_key = task.properties.get("output_key", "conceptual_memory_update")

        result = {"updated": False, "concept": None}

        if not workflow_name or not goal:
            logger.info("UpdateConceptualMemoryAction: missing workflow_name or goal — skipping")
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        memory_store = context.extras.get("__memory_store__")
        if memory_store is None:
            logger.info("UpdateConceptualMemoryAction: no memory store — skipping")
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        try:
            # Get existing conceptual memory for context
            existing_context = await memory_store.get_conceptual_context_for_llm()
            existing_entries = await memory_store.get_conceptual_memories(limit=50)

            # Get recent workflow memory for this workflow (for rating context)
            wf_memories = await memory_store.get_workflow_memories(workflow_name, limit=5)
            ratings = [m.rating for m in wf_memories if m.rating is not None]
            avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
            use_count = len(wf_memories)

            # Build LLM prompt
            status = "SUCCESS" if success else "FAILURE"
            prompt = (
                f"Recent run:\n"
                f"  Workflow: {workflow_name}\n"
                f"  Goal: {goal}\n"
                f"  Result: {status}\n"
                f"  Notes: {effectiveness_notes or 'None'}\n"
                f"  Use count for this workflow: {use_count}\n"
            )
            if avg_rating:
                prompt += f"  Avg rating: {avg_rating}/5\n"

            if existing_context:
                prompt += f"\nExisting conceptual memory:\n{existing_context}"
            else:
                prompt += "\nNo existing conceptual memory yet — create the first entry."

            provider = get_provider(provider_name, model)
            response = await provider.complete(
                messages=[
                    Message.system(self.SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.3,
                max_tokens=600,
            )

            content = response.content or "{}"
            # Strip markdown
            if "```" in content:
                import re

                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

            data = json.loads(content)
            concept_label = data.get("concept", "")
            recommended = data.get("recommended_workflows", [])
            anti_patterns = data.get("anti_patterns", "")

            if not concept_label:
                logger.warning("UpdateConceptualMemoryAction: LLM returned empty concept label")
                context.set_process_property(output_key, result)
                return TaskResult.ok(output=result)

            # Find existing entry with matching concept label (exact match for now)
            existing_entry = next(
                (e for e in existing_entries if e.concept.lower() == concept_label.lower()), None
            )

            from zebra_agent.memory import ConceptualMemoryEntry

            if existing_entry is not None:
                # Update in-place: merge recommended workflows
                existing_names = {wf["name"] for wf in existing_entry.recommended_workflows}
                merged = list(existing_entry.recommended_workflows)
                for wf in recommended:
                    if wf.get("name") not in existing_names:
                        merged.append(wf)
                    else:
                        # Update existing entry's fit_notes and use_count
                        for existing_wf in merged:
                            if existing_wf["name"] == wf.get("name"):
                                existing_wf["fit_notes"] = wf.get(
                                    "fit_notes", existing_wf.get("fit_notes", "")
                                )
                                existing_wf["use_count"] = existing_wf.get("use_count", 0) + 1
                                if avg_rating:
                                    existing_wf["avg_rating"] = avg_rating
                                break

                from datetime import datetime

                updated_entry = ConceptualMemoryEntry(
                    id=existing_entry.id,
                    concept=concept_label,
                    recommended_workflows=merged,
                    anti_patterns=anti_patterns or existing_entry.anti_patterns,
                    last_updated=datetime.now(UTC),
                    tokens=existing_entry.tokens,
                )
            else:
                updated_entry = ConceptualMemoryEntry.create(
                    concept=concept_label,
                    recommended_workflows=recommended,
                    anti_patterns=anti_patterns,
                )

            await memory_store.save_conceptual_memory(updated_entry)
            logger.info(f"UpdateConceptualMemoryAction: updated concept '{concept_label}'")

            result = {"updated": True, "concept": concept_label}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        except Exception as e:
            logger.warning(f"UpdateConceptualMemoryAction: failed — degrading gracefully: {e}")
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

    def _resolve(
        self, task: TaskInstance, context: ExecutionContext, key: str, default: str
    ) -> str:
        value = task.properties.get(key, default)
        if isinstance(value, str) and "{{" in value:
            value = context.resolve_template(value)
        return value or default

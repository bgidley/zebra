"""CompactMemoryAction — enforce hot/warm/cold tiered retention on agent memory."""

import json
import logging
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

_WARM_WORKFLOW_PROMPT = (
    'You are summarising an old workflow run record. Compress the following '
    'output summary and effectiveness notes into a single concise digest of '
    'at most 150 tokens. Keep the most important outcome and any key lessons. '
    'Return JSON only: {{"digest": "..."}}\n\n'
    "Output summary: {output_summary}\n"
    "Effectiveness notes: {effectiveness_notes}"
)

_WARM_ANTI_PATTERNS_PROMPT = (
    'Compress the following anti-patterns text to at most 100 tokens. '
    'Preserve the key warnings. Return JSON only: {{"compressed": "..."}}\n\n'
    "{anti_patterns}"
)


class CompactMemoryAction(TaskAction):
    """Enforce tiered retention on WorkflowMemoryEntry and ConceptualMemoryEntry.

    Hot  (< 2 weeks):  full detail, no change.
    Warm (2w–2mo):     LLM-compress output_summary+effectiveness_notes (workflow);
                       trim recommended_workflows to top-3 + compress anti_patterns
                       (conceptual).
    Cold (> 2mo):      clear output_summary and effectiveness_notes (workflow);
                       trim recommended_workflows to top-1, clear anti_patterns
                       (conceptual).

    Reads ``__memory_store__`` from context.extras. Degrades gracefully if absent.
    """

    description = "Enforce hot/warm/cold tiered retention on agent memory entries."

    inputs = [
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
            default="compaction_result",
        ),
    ]

    outputs = [
        ParameterDef(name="warm_workflow", type="int", description="Workflow entries compressed"),
        ParameterDef(name="cold_workflow", type="int", description="Workflow entries stripped"),
        ParameterDef(
            name="warm_conceptual", type="int", description="Conceptual entries compressed"
        ),
        ParameterDef(name="cold_conceptual", type="int", description="Conceptual entries stripped"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Run one compaction pass."""
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")
        output_key = task.properties.get("output_key", "compaction_result")

        result = {
            "warm_workflow": 0,
            "cold_workflow": 0,
            "warm_conceptual": 0,
            "cold_conceptual": 0,
        }

        memory_store = context.extras.get("__memory_store__")
        if memory_store is None:
            logger.info("CompactMemoryAction: no memory store — skipping")
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        now = datetime.now(UTC)
        try:
            batch = await memory_store.get_entries_for_compaction(now)
        except Exception:
            logger.warning("CompactMemoryAction: get_entries_for_compaction failed", exc_info=True)
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        if batch.is_empty():
            logger.info("CompactMemoryAction: nothing to compact")
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        provider = get_provider(provider_name, model)

        # ── Warm workflow entries: LLM compress ─────────────────────────────
        for entry in batch.warm_workflow:
            try:
                digest = await self._compress_workflow_entry(provider, entry)
                await memory_store.update_workflow_memory_tier(
                    entry.id,
                    tier="warm",
                    output_summary=digest,
                    effectiveness_notes="",
                )
                result["warm_workflow"] += 1
            except Exception:
                logger.warning(
                    "CompactMemoryAction: warm compression failed for %s — skipping",
                    entry.id,
                    exc_info=True,
                )

        # ── Cold workflow entries: strip ────────────────────────────────────
        for entry in batch.cold_workflow:
            try:
                await memory_store.update_workflow_memory_tier(
                    entry.id,
                    tier="cold",
                    output_summary="",
                    effectiveness_notes="",
                )
                result["cold_workflow"] += 1
            except Exception:
                logger.warning(
                    "CompactMemoryAction: cold strip failed for %s — skipping",
                    entry.id,
                    exc_info=True,
                )

        # ── Warm conceptual entries: trim + compress ────────────────────────
        for entry in batch.warm_conceptual:
            try:
                trimmed = self._top_n_workflows(entry.recommended_workflows, 3)
                compressed_ap = await self._compress_anti_patterns(provider, entry.anti_patterns)
                await memory_store.update_conceptual_memory_tier(
                    entry.id,
                    tier="warm",
                    recommended_workflows=trimmed,
                    anti_patterns=compressed_ap,
                )
                result["warm_conceptual"] += 1
            except Exception:
                logger.warning(
                    "CompactMemoryAction: warm conceptual failed for %s — skipping",
                    entry.id,
                    exc_info=True,
                )

        # ── Cold conceptual entries: strip to top-1 ─────────────────────────
        for entry in batch.cold_conceptual:
            try:
                top1 = self._top_n_workflows(entry.recommended_workflows, 1)
                await memory_store.update_conceptual_memory_tier(
                    entry.id,
                    tier="cold",
                    recommended_workflows=top1,
                    anti_patterns="",
                )
                result["cold_conceptual"] += 1
            except Exception:
                logger.warning(
                    "CompactMemoryAction: cold conceptual failed for %s — skipping",
                    entry.id,
                    exc_info=True,
                )

        logger.info(
            "CompactMemoryAction: done — warm_wf=%d cold_wf=%d warm_cm=%d cold_cm=%d",
            result["warm_workflow"],
            result["cold_workflow"],
            result["warm_conceptual"],
            result["cold_conceptual"],
        )
        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)

    async def _compress_workflow_entry(self, provider, entry) -> str:
        """LLM-compress output_summary + effectiveness_notes into a short digest."""
        prompt = _WARM_WORKFLOW_PROMPT.format(
            output_summary=entry.output_summary[:800],
            effectiveness_notes=entry.effectiveness_notes[:400],
        )
        response = await provider.complete(
            messages=[Message.user(prompt)],
            temperature=0.1,
            max_tokens=200,
        )
        content = response.content or "{}"
        content = self._strip_markdown(content)
        data = json.loads(content)
        return data.get("digest", entry.output_summary[:300])

    async def _compress_anti_patterns(self, provider, anti_patterns: str) -> str:
        """LLM-compress anti_patterns text."""
        if not anti_patterns:
            return ""
        prompt = _WARM_ANTI_PATTERNS_PROMPT.format(anti_patterns=anti_patterns[:600])
        response = await provider.complete(
            messages=[Message.user(prompt)],
            temperature=0.1,
            max_tokens=150,
        )
        content = response.content or "{}"
        content = self._strip_markdown(content)
        data = json.loads(content)
        return data.get("compressed", anti_patterns[:300])

    @staticmethod
    def _top_n_workflows(workflows: list[dict], n: int) -> list[dict]:
        """Return the top-N workflows by use_count."""
        return sorted(workflows, key=lambda w: w.get("use_count", 0), reverse=True)[:n]

    @staticmethod
    def _strip_markdown(content: str) -> str:
        import re

        if "```" in content:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                return match.group(1)
        return content

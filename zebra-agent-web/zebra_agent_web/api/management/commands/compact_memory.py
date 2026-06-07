"""Django management command: run one memory compaction pass.

Usage:
    python manage.py compact_memory

Classifies all WorkflowMemoryEntry and ConceptualMemoryEntry records into
hot/warm/cold tiers and compacts those that have crossed a boundary since
their last compaction.  Exits 0 on success.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run one memory compaction pass (hot/warm/cold tiered retention)."

    def handle(self, *args, **options):
        asyncio.run(self._run())

    async def _run(self):
        from zebra_agent_web.api import agent_engine

        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()

        if agent_loop.memory is None:
            self.stderr.write("No memory store available — nothing to compact.")
            return

        from zebra_tasks.agent.compact_memory import CompactMemoryAction
        from zebra_tasks.llm.providers import get_provider

        now = datetime.now(UTC)
        batch = await agent_loop.memory.get_entries_for_compaction(now)

        if batch.is_empty():
            self.stdout.write("Nothing to compact.")
            return

        self.stdout.write(
            f"Compacting: warm_wf={len(batch.warm_workflow)} "
            f"cold_wf={len(batch.cold_workflow)} "
            f"warm_cm={len(batch.warm_conceptual)} "
            f"cold_cm={len(batch.cold_conceptual)}"
        )

        action = CompactMemoryAction()
        provider = get_provider("anthropic")

        # Warm workflow
        for entry in batch.warm_workflow:
            try:
                digest = await action._compress_workflow_entry(provider, entry)
                await agent_loop.memory.update_workflow_memory_tier(
                    entry.id, tier="warm", output_summary=digest, effectiveness_notes=""
                )
            except Exception as exc:
                self.stderr.write(f"Warm workflow {entry.id[:8]}: {exc}")

        # Cold workflow
        for entry in batch.cold_workflow:
            try:
                await agent_loop.memory.update_workflow_memory_tier(
                    entry.id, tier="cold", output_summary="", effectiveness_notes=""
                )
            except Exception as exc:
                self.stderr.write(f"Cold workflow {entry.id[:8]}: {exc}")

        # Warm conceptual
        for entry in batch.warm_conceptual:
            try:
                trimmed = action._top_n_workflows(entry.recommended_workflows, 3)
                compressed_ap = await action._compress_anti_patterns(provider, entry.anti_patterns)
                await agent_loop.memory.update_conceptual_memory_tier(
                    entry.id,
                    tier="warm",
                    recommended_workflows=trimmed,
                    anti_patterns=compressed_ap,
                )
            except Exception as exc:
                self.stderr.write(f"Warm conceptual {entry.id[:8]}: {exc}")

        # Cold conceptual
        for entry in batch.cold_conceptual:
            try:
                top1 = action._top_n_workflows(entry.recommended_workflows, 1)
                await agent_loop.memory.update_conceptual_memory_tier(
                    entry.id, tier="cold", recommended_workflows=top1, anti_patterns=""
                )
            except Exception as exc:
                self.stderr.write(f"Cold conceptual {entry.id[:8]}: {exc}")

        self.stdout.write(self.style.SUCCESS("Compaction complete."))

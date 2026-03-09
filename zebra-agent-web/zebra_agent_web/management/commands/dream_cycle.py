"""Django management command to run the Dream Cycle self-improvement workflow.

Usage:
    python manage.py dream_cycle
    python manage.py dream_cycle --dry-run

This can be scheduled via cron, systemd timer, or any task scheduler:
    0 3 * * * cd /path/to/project && python manage.py dream_cycle
"""

import asyncio
import json
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Dream Cycle self-improvement workflow to analyze and optimize agent workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview changes without saving them.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write("Running dream cycle in dry-run mode (no changes will be saved)...")
        else:
            self.stdout.write("Running dream cycle...")

        try:
            result = asyncio.run(self._run_dream_cycle(dry_run))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Dream cycle failed: {e}"))
            logger.exception("Dream cycle management command failed")
            raise

        if result.get("success"):
            self.stdout.write(self.style.SUCCESS("Dream cycle completed successfully."))

            summary = result.get("dream_summary")
            if summary:
                self.stdout.write(f"\n{summary}")

            metrics = result.get("metrics_analysis") or {}
            self.stdout.write(
                f"\nAnalyzed {metrics.get('total_runs_analyzed', 0)} runs "
                f"across {metrics.get('unique_workflows', 0)} workflows "
                f"over {metrics.get('analysis_period_days', 0)} days."
            )

            opt = result.get("optimization_results") or {}
            changes = opt.get("changes_made", [])
            if changes:
                self.stdout.write(f"\nChanges made: {len(changes)}")
                for change in changes:
                    self.stdout.write(f"  - [{change.get('type')}] {change.get('workflow', '')}")
            else:
                self.stdout.write("\nNo changes were made.")

        else:
            error = result.get("error", "Unknown error")
            self.stderr.write(self.style.ERROR(f"Dream cycle failed: {error}"))

    async def _run_dream_cycle(self, dry_run: bool) -> dict:
        """Initialize the agent engine and run the dream cycle."""
        from zebra_agent_web.api import agent_engine

        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()

        async def _progress(event: str, data: dict) -> None:
            """Log progress events to stdout."""
            logger.info(f"Dream cycle event: {event} {json.dumps(data, default=str)}")

        return await agent_loop.run_dream_cycle(progress_callback=_progress)

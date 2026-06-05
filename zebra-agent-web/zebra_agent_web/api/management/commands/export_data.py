"""Django management command to export all user data to a ZIP archive.

Usage:
    python manage.py export_data --user 1 --out zebra-export.zip

The archive contains:
    manifest.json   — format version, user_id, export timestamp
    processes.json  — all process instances and their tasks
    memory.json     — workflow memory + conceptual memory entries
    metrics.json    — workflow run records
    knowledge.json  — personal knowledge entries
    workflows/      — YAML workflow files
"""

import asyncio
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Export all data for a user to a portable ZIP archive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            required=True,
            help="User ID (integer) to export data for.",
        )
        parser.add_argument(
            "--out",
            default="zebra-export.zip",
            help="Output file path (default: zebra-export.zip).",
        )

    def handle(self, *args, **options):
        user_id = options["user"]
        out_path = Path(options["out"])

        self.stdout.write(f"Exporting data for user {user_id!r} to {out_path} ...")

        try:
            archive_bytes = asyncio.run(self._export(user_id))
        except Exception as exc:
            raise CommandError(f"Export failed: {exc}") from exc

        out_path.write_bytes(archive_bytes)
        self.stdout.write(
            self.style.SUCCESS(f"Export complete: {out_path} ({len(archive_bytes):,} bytes)")
        )

    async def _export(self, user_id: str) -> bytes:
        """Initialise agent engine and run the export."""
        from zebra_agent.export import DataExporter

        from zebra_agent_web.api import agent_engine, engine

        await agent_engine.ensure_initialized()
        await engine.ensure_initialized()

        exporter = DataExporter()
        return await exporter.export_user_data(
            user_id=user_id,
            memory_store=agent_engine.get_memory(),
            metrics_store=agent_engine.get_metrics(),
            knowledge_store=agent_engine.get_knowledge(),
            process_store=engine.get_store(),
            workflow_library=agent_engine.get_library(),
        )

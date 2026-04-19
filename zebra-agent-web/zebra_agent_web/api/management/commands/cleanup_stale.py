"""Django management command: clean up stale/stuck workflows.

Usage:
    python manage.py cleanup_stale                     # dry-run by default
    python manage.py cleanup_stale --hours 24 --cancel # cancel stale processes
    python manage.py cleanup_stale --hours 48 --delete # hard-delete stale processes
    python manage.py cleanup_stale --cancel --all      # cancel ALL running (no age filter)

Finds RUNNING processes whose updated_at is older than --hours (default 24)
and either cancels (fail_process) or deletes (delete_process) them.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Find and clean up stale/stuck RUNNING processes. "
        "By default performs a dry-run; use --cancel or --delete to act."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Staleness threshold in hours (default: 24). "
            "Processes with updated_at older than this are considered stale.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Target ALL running processes regardless of age.",
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--cancel",
            action="store_true",
            default=False,
            help="Cancel stale processes (move to FAILED state, preserves data).",
        )
        group.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Hard-delete stale processes (removes all data permanently).",
        )

    def handle(self, *args, **options):
        try:
            asyncio.run(self._run(options))
        except KeyboardInterrupt:
            self.stdout.write("\nAborted.")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
            sys.exit(1)

    async def _run(self, options: dict) -> None:
        from zebra_agent_web.api import engine as engine_module

        await engine_module.ensure_initialized()
        store = engine_module.get_store()
        wf_engine = engine_module.get_engine()

        # Find running processes
        running = await store.get_running_processes()
        if not running:
            self.stdout.write(self.style.SUCCESS("No running processes found."))
            return

        # Filter by age unless --all
        if options["all"]:
            stale = running
        else:
            cutoff = datetime.now(UTC) - timedelta(hours=options["hours"])
            stale = [p for p in running if p.updated_at < cutoff]

        if not stale:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No stale processes found (threshold: {options['hours']}h, "
                    f"{len(running)} running)."
                )
            )
            return

        # Display what we found
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Found {len(stale)} stale process(es) (out of {len(running)} running):"
            )
        )
        for p in stale:
            goal = (p.properties or {}).get("goal", "—")
            self.stdout.write(
                f'  {p.id[:12]}...  updated={p.updated_at:%Y-%m-%d %H:%M}  goal="{goal[:60]}"'
            )

        # Dry-run by default
        if not options["cancel"] and not options["delete"]:
            self.stdout.write(
                self.style.WARNING("\nDry-run mode. Use --cancel or --delete to act.")
            )
            return

        # Act
        action = "cancel" if options["cancel"] else "delete"
        self.stdout.write(f"\n{action.title()}ling {len(stale)} process(es)...")

        cancelled = 0
        errors = 0
        for p in stale:
            try:
                if options["cancel"]:
                    await wf_engine.fail_process(p.id, "Cleaned up by cleanup_stale command")
                else:
                    await store.delete_process(p.id)
                cancelled += 1
                self.stdout.write(f"  {self.style.SUCCESS('OK')}  {p.id[:12]}...")
            except Exception as e:
                errors += 1
                self.stdout.write(f"  {self.style.ERROR('FAIL')}  {p.id[:12]}... — {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone: {cancelled} {action}led, {errors} error(s).")
        )

"""Django management command: budget-aware goal execution daemon.

Usage:
    python manage.py run_daemon
    python manage.py run_daemon --daily-budget 25.0
    python manage.py run_daemon --poll-interval 15 --dry-run

Runs forever.  Picks the highest-priority CREATED process, checks the budget,
starts it, waits for completion, logs cost, and repeats.

NOTE: The daemon also auto-starts as a background task inside the ASGI server.
This standalone command is only needed if you want to run the daemon in a
separate process (e.g. for production deployments or when the web server is
not running).
"""

from __future__ import annotations

import asyncio
import signal
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run the budget daemon — continuously picks queued goals and "
        "executes them within the daily dollar budget."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--daily-budget",
            type=float,
            default=None,
            help="Override DAILY_BUDGET_USD setting (dollars).",
        )
        parser.add_argument(
            "--poll-interval",
            type=int,
            default=None,
            help="Override DAEMON_POLL_INTERVAL setting (seconds).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would happen without starting any goals.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Starting budget daemon..."))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("  DRY-RUN mode — no goals will be started"))

        try:
            asyncio.run(self._run(options))
        except KeyboardInterrupt:
            self.stdout.write("\nShutting down daemon.")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Daemon crashed: {e}"))
            import logging

            logging.getLogger(__name__).exception("Daemon crashed")
            sys.exit(1)

    async def _run(self, options: dict) -> None:
        """Bootstrap and delegate to the shared daemon loop."""
        from zebra_agent_web.api.daemon import run_daemon_loop

        stop_event = asyncio.Event()

        # Graceful shutdown on SIGTERM / SIGINT
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        await run_daemon_loop(
            stop_event,
            daily_budget=options["daily_budget"],
            poll_interval=options["poll_interval"],
        )

"""Django management command: activate or deactivate the kill switch.

Usage:
    python manage.py kill_switch --status
    python manage.py kill_switch --halt [--reason "scheduled maintenance"]
    python manage.py kill_switch --resume
"""

from __future__ import annotations

import sys

import django
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Activate or deactivate the system-wide kill switch."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--halt",
            action="store_true",
            default=False,
            help="Activate the kill switch — daemon stops picking up new processes.",
        )
        group.add_argument(
            "--resume",
            action="store_true",
            default=False,
            help="Deactivate the kill switch — daemon resumes normal operation.",
        )
        group.add_argument(
            "--status",
            action="store_true",
            default=False,
            help="Show current kill-switch status.",
        )
        parser.add_argument(
            "--reason",
            default="",
            help="Optional reason to record when halting.",
        )

    def handle(self, *args, **options):
        django.setup() if not django.conf.settings.configured else None

        from zebra_agent_web.api.kill_switch import get_status_sync, set_halted_sync

        try:
            if options["status"]:
                info = get_status_sync()
                self._print_status(info)

            elif options["halt"]:
                info = set_halted_sync(True, reason=options["reason"])
                self.stdout.write(self.style.WARNING("Kill switch ACTIVATED."))
                self._print_status(info)

            elif options["resume"]:
                info = set_halted_sync(False)
                self.stdout.write(
                    self.style.SUCCESS("Kill switch deactivated — daemon will resume.")
                )
                self._print_status(info)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
            sys.exit(1)

    def _print_status(self, info: dict) -> None:
        halted = info["halted"]
        label = self.style.WARNING("HALTED") if halted else self.style.SUCCESS("active")
        self.stdout.write(f"  Status    : {label}")
        if halted:
            self.stdout.write(f"  Halted at : {info['halted_at']}")
            if info["halted_reason"]:
                self.stdout.write(f"  Reason    : {info['halted_reason']}")

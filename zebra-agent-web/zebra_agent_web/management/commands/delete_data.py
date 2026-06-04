"""Django management command to delete all data scoped to a user (REQ-DATA-005 / F10).

Usage:
    python manage.py delete_data --user <user_id_or_username>
    python manage.py delete_data --user 1 --hard
    python manage.py delete_data --user 1 --hard --yes   # skip confirmation

Soft delete (default):
    Only soft-deletes knowledge entries (sets deleted_at). Other records with no
    soft-delete column are unaffected.

Hard delete (--hard):
    Permanently removes every row scoped to the user from all tables:
    processes, tasks, FOEs, workflow runs, memories, knowledge, values profile.
    Ethics audit entries are intentionally retained (append-only audit trail).
    This operation is IRREVERSIBLE.
"""

import asyncio
import logging
import sys

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete all data scoped to a user. "
        "Use --hard for physical removal, otherwise only soft-deletes knowledge entries."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            required=True,
            help="User ID (integer) or username of the user whose data will be deleted.",
        )
        parser.add_argument(
            "--hard",
            action="store_true",
            default=False,
            help=(
                "Permanently delete all user-scoped rows. "
                "Default is soft delete (knowledge entries only). "
                "WARNING: this is irreversible."
            ),
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help="Skip the confirmation prompt.",
        )

    def handle(self, *args, **options):
        user_arg = options["user"]
        hard = options["hard"]
        yes = options["yes"]

        user_id = self._resolve_user(user_arg)

        mode_label = "HARD (permanent)" if hard else "soft"
        self.stdout.write(
            f"About to perform a {mode_label} delete of all data for user ID {user_id}."
        )

        if hard:
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: Hard delete is irreversible. "
                    "All processes, runs, memories, knowledge, and profile data will be removed."
                )
            )

        if not yes:
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            if confirm != "yes":
                self.stdout.write("Aborted.")
                sys.exit(0)

        try:
            report = asyncio.run(self._run_deletion(user_id, hard))
        except Exception as e:
            logger.exception("Data deletion failed")
            raise CommandError(f"Deletion failed: {e}") from e

        if report.errors:
            for err in report.errors:
                self.stderr.write(self.style.ERROR(f"  Error: {err}"))

        d = report.as_dict()
        totals = d["totals"]
        self.stdout.write(self.style.SUCCESS(f"\nDeletion complete (user_id={user_id})."))
        self.stdout.write(f"  Mode: {'hard' if hard else 'soft'}")
        self.stdout.write(f"  Grand total affected: {totals['grand_total']}")
        if hard:
            self.stdout.write(f"    Processes:           {totals['processes']}")
            self.stdout.write(f"    Tasks:               {totals['tasks']}")
            self.stdout.write(f"    Flows of execution:  {totals['flows_of_execution']}")
            self.stdout.write(f"    Process locks:       {totals['process_locks']}")
            self.stdout.write(f"    Workflow runs:       {totals['workflow_runs']}")
            self.stdout.write(f"    Workflow memories:   {totals['workflow_memories']}")
            self.stdout.write(f"    Conceptual memories: {totals['conceptual_memories']}")
            self.stdout.write(f"    Knowledge entries:   {totals['knowledge_entries']}")
            self.stdout.write(f"    Profile versions:    {totals['profile_versions']}")
            self.stdout.write(f"    Profiles:            {totals['profiles']}")
        else:
            self.stdout.write(f"    Knowledge entries soft-deleted: {totals['knowledge_entries']}")

    def _resolve_user(self, user_arg: str) -> int:
        """Resolve a user_id (int string) or username to an integer user ID."""
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Try integer first
        try:
            user_id = int(user_arg)
            if not User.objects.filter(pk=user_id).exists():
                raise CommandError(f"No user found with ID {user_id}.")
            return user_id
        except ValueError:
            pass

        # Try username
        try:
            user = User.objects.get(username=user_arg)
            return user.pk
        except User.DoesNotExist:
            raise CommandError(f"No user found with username '{user_arg}'.")

    async def _run_deletion(self, user_id: int, hard: bool):
        from zebra_agent.deletion import DataDeletor

        deletor = DataDeletor()
        return await deletor.delete_user_data(user_id, hard=hard)

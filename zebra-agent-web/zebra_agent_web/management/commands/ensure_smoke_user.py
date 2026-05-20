"""Management command to create or update the smoke test user."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the smoke test user for CI smoke tests"

    def add_arguments(self, parser):
        parser.add_argument("password", type=str, help="Password for the smoke user")

    def handle(self, *args, **options):
        u, created = User.objects.get_or_create(username="smoke")
        u.set_password(options["password"])
        u.save()
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} smoke user"))

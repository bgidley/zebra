"""Django management command: print a short-lived login session for the smoke user.

Usage:
    python manage.py smoke_session [--username smoke] [--minutes 15]

Prints only the session key, for the post-deploy ``smoke`` job's
``ZEBRA_SMOKE_SESSION`` (#218). Login is passkey-only, so without this the
smoke tests of logged-in pages always skipped. The deploy creates the user
(``SMOKE_PASSWORD``); exits 1 when it does not exist.
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.core.management.base import BaseCommand, CommandError


def create_session(user, minutes: int) -> str:
    """Create a session logged in as *user* that expires after *minutes*; return its key."""
    session = import_module(settings.SESSION_ENGINE).SessionStore()
    session[SESSION_KEY] = user._meta.pk.value_to_string(user)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.set_expiry(minutes * 60)
    session.create()
    return session.session_key


class Command(BaseCommand):
    help = "Print a short-lived session key for the smoke user (post-deploy smoke tests)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="smoke", help="User to log in as")
        parser.add_argument("--minutes", type=int, default=15, help="Session lifetime")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"], is_active=True)
        user = user.first()
        if user is None:
            raise CommandError(f"No active user {options['username']!r}")
        self.stdout.write(create_session(user, options["minutes"]))

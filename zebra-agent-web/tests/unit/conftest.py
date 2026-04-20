"""Test configuration for zebra-agent-web unit tests.

Sets up Django so that models and ORM are available for tests that need them.
Tests using @pytest.mark.django_db get an isolated SQLite test database.

Uses test_settings.py which overrides DATABASES to SQLite so we don't need
an Oracle instance to run these unit tests.
"""

import os

import django

# Force override — CI sets DJANGO_SETTINGS_MODULE=zebra_agent_web.settings globally,
# but unit tests must use SQLite. setdefault() would be a no-op in that environment.
os.environ["DJANGO_SETTINGS_MODULE"] = "zebra_agent_web.test_settings"
django.setup()

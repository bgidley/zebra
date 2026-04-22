"""Test configuration for zebra-agent-web unit tests.

Sets up Django so that models and ORM are available for tests that need them.
Tests using @pytest.mark.django_db get an isolated SQLite test database.

Uses test_settings.py which overrides DATABASES to SQLite so we don't need
an Oracle instance to run these unit tests.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.test_settings")
# Allow sync ORM calls from async test contexts (pytest-asyncio runs an event loop)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
django.setup()

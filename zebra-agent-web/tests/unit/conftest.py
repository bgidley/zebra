"""Test configuration for zebra-agent-web unit tests.

Sets up Django so that models and ORM are available for tests that need them.
Tests using @pytest.mark.django_db get an isolated SQLite test database.

Uses test_settings.py which overrides DATABASES to SQLite so we don't need
an Oracle instance to run these unit tests.
"""

import os

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.test_settings")
# Allow sync ORM calls from async test contexts (pytest-asyncio runs an event loop)
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
django.setup()


@pytest.fixture
def test_user(db):
    """Create a test user for authentication."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(username="testuser")


@pytest.fixture
def authenticated_client(client, test_user):
    """Return a sync client authenticated as test_user."""
    client.force_login(test_user)
    return client


@pytest.fixture
def authenticated_async_client(async_client, test_user):
    """Return an async client authenticated as test_user."""
    async_client.force_login(test_user)
    return async_client

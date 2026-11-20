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


# ---------------------------------------------------------------------------
# Onboarding wizard (#276)
# ---------------------------------------------------------------------------


async def _onboarding_noop() -> None:
    return None


@pytest.fixture
def onboarding_env(db, tmp_path, settings, monkeypatch):
    """A DjangoStore engine + a library holding the shipped *Onboarding* built-in, with
    onboarding switched on (env and owner) and the rate-limit cache cleared.

    Returns ``(engine, library)``.
    """
    import shutil

    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module
    from django.core.cache import cache
    from zebra.core.engine import WorkflowEngine
    from zebra.tasks.registry import ActionRegistry
    from zebra_agent.library import BUILTIN_WORKFLOWS_DIR, WorkflowLibrary
    from zebra_agent_web.api import onboarding
    from zebra_agent_web.api.identity import set_identity_sync
    from zebra_agent_web.api.models import SystemStateModel
    from zebra_agent_web.storage import DjangoStore

    shipped = tmp_path / "shipped"
    shipped.mkdir()
    shutil.copy(BUILTIN_WORKFLOWS_DIR / "onboarding.yaml", shipped / "onboarding.yaml")
    library = WorkflowLibrary(tmp_path / "library")
    library.copy_builtin_workflows(shipped)

    store = DjangoStore()
    registry = ActionRegistry()
    registry.register_defaults()
    wf_engine = WorkflowEngine(store, registry)

    monkeypatch.setattr(engine_module, "_store", store)
    monkeypatch.setattr(engine_module, "_engine", wf_engine)
    monkeypatch.setattr(agent_engine_module, "_library", library)
    monkeypatch.setattr(agent_engine_module, "ensure_initialized", _onboarding_noop)
    monkeypatch.setattr(engine_module, "ensure_initialized", _onboarding_noop)
    monkeypatch.setattr(onboarding, "_last_expiry_check", 0.0)

    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": True}
    set_identity_sync("Test User")
    SystemStateModel.objects.update_or_create(pk=1, defaults={"onboarding_enabled": True})
    cache.clear()
    yield wf_engine, library
    cache.clear()

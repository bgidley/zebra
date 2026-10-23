"""manage.py smoke_session (#218): a short-lived login for the post-deploy smoke tests."""

from importlib import import_module
from io import StringIO

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from zebra.storage.memory import InMemoryStore
from zebra_agent_web.api import engine


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def empty_store(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr(engine, "ensure_initialized", _noop)
    monkeypatch.setattr(engine, "get_store", lambda: InMemoryStore())


def _session(*args: str) -> str:
    out = StringIO()
    call_command("smoke_session", *args, stdout=out)
    return out.getvalue().strip()


def test_session_logs_in_the_smoke_user(client, completed_setup, empty_store):
    get_user_model().objects.create_user("smoke", password="x")
    client.cookies["sessionid"] = _session()

    inbox = client.get("/tasks/")
    badge = client.get("/nav/needs-you/")

    # Unit settings drop LoginRequiredMiddleware, so check who the request ran as.
    assert inbox.wsgi_request.user.username == "smoke"
    assert inbox.status_code == 200
    assert 'data-testid="inbox-empty"' in inbox.content.decode()
    assert badge.status_code == 200
    assert 'data-testid="nav-needs-you"' in badge.content.decode()


def test_session_expires(db):
    get_user_model().objects.create_user("smoke", password="x")

    key = _session("--minutes", "5")

    session = import_module(settings.SESSION_ENGINE).SessionStore(session_key=key)
    assert session.get_expiry_age() == 300


def test_missing_user_fails(db):
    with pytest.raises(CommandError, match="smoke"):
        _session()


def test_inactive_user_fails(db):
    get_user_model().objects.create_user("smoke", password="x", is_active=False)

    with pytest.raises(CommandError):
        _session()

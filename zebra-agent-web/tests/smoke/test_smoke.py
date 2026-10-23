"""Smoke tests executed against a live podman container.

These tests make real HTTP requests to verify the container stack is healthy:
image built correctly, entrypoint ran, migrations applied, Daphne serving.
"""

import pytest

pytestmark = pytest.mark.smoke


async def test_login_page_loads(client):
    """Container is reachable and serving the login page."""
    r = await client.get("/auth/login/")
    assert r.status_code == 200
    assert "login" in r.text.lower()


async def test_dashboard_accessible(logged_in_client):
    """Dashboard loads for an authenticated user."""
    r = await logged_in_client.get("/")
    assert r.status_code == 200
    assert "/auth/login/" not in str(r.url)


async def test_tasks_inbox(logged_in_client):
    """The /tasks/ inbox renders its list or its empty state, not the login page (#218)."""
    r = await logged_in_client.get("/tasks/")
    assert r.status_code == 200
    assert "/auth/login/" not in str(r.url)
    assert 'data-testid="inbox"' in r.text or 'data-testid="inbox-empty"' in r.text
    assert 'data-testid="inbox-error"' not in r.text


async def test_needs_you_badge(logged_in_client):
    """The nav badge partial the inbox count is loaded from (#218)."""
    r = await logged_in_client.get("/nav/needs-you/")
    assert r.status_code == 200
    assert 'data-testid="nav-needs-you"' in r.text


async def test_health_api(client):
    """Health endpoint reports the container as healthy."""
    r = await client.get("/api/health/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy", f"Unexpected health response: {data}"


async def test_budget_api(logged_in_client):
    """Budget API returns a valid JSON response."""
    r = await logged_in_client.get("/api/budget/")
    assert r.status_code == 200
    data = r.json()
    assert "daily_budget" in data

"""Fixtures for smoke tests against a live podman container.

Set ZEBRA_SMOKE_URL to point at the running container (default: http://localhost:8001).
The smoke user must already exist in the container DB (created by the CI job via
manage.py shell -c before tests run).
"""

import os
import re

import httpx
import pytest

BASE_URL = os.environ.get("ZEBRA_SMOKE_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
async def client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=True) as c:
        yield c


@pytest.fixture
async def logged_in_client(client: httpx.AsyncClient):
    """Return a client authenticated as the smoke user."""
    r = await client.get("/accounts/login/")
    assert r.status_code == 200, f"Login page returned {r.status_code}"

    # Extract CSRF token from cookie or hidden input
    token = client.cookies.get("csrftoken")
    if not token:
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        assert m, "Could not find CSRF token on login page"
        token = m.group(1)

    resp = await client.post(
        "/accounts/login/",
        data={
            "username": "smoke",
            "password": "smokepass123",
            "csrfmiddlewaretoken": token,
        },
        headers={"Referer": f"{BASE_URL}/accounts/login/"},
    )
    assert resp.status_code == 200, f"Login failed with status {resp.status_code}"
    yield client
